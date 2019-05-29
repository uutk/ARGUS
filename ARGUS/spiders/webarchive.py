# -*- coding: utf-8 -*-
import scrapy
import tldextract
from ARGUS.items import Collector
from scrapy.loader import ItemLoader
from scrapy.utils.request import request_fingerprint
import re
from scrapy.spidermiddlewares.httperror import HttpError
from twisted.internet.error import DNSLookupError
from twisted.internet.error import TimeoutError, TCPTimedOutError
import pandas as pd
import copy
import requests


class webarchiveSpider(scrapy.Spider):
    name = 'webarchive'
    custom_settings = {
        'ITEM_PIPELINES': {
            'ARGUS.pipelines.TextPipeline': 300
        }
    }

##################################################################
# INIT
##################################################################
    
    #load URLs from text file defined in given parameter
    def __init__(self, url_chunk="", limit=5, ID="ID", url_col="url", language="", prefer_short_urls="on", date="", *args, **kwargs):
        super(webarchiveSpider, self).__init__(*args, **kwargs)
        #loads urls and IDs from text file
        data = pd.read_csv(url_chunk, delimiter="\t", encoding="utf-8", error_bad_lines=False, engine="python")
        self.allowed_domains = [url.split("www.")[-1].lower() for url in list(data[url_col])]
        self.start_urls = ["http://" + url.lower() for url in self.allowed_domains]
        self.IDs = [ID for ID in list(data[ID])]
        self.site_limit = int(limit)
        self.url_chunk = url_chunk
        self.language = language.split(",")
        self.prefer_short_urls = prefer_short_urls
        self.date = date
        self.allowed_domains.append ("web.archive.org")
    
##################################################################
# HELPER FUNCTIONS
##################################################################
 
    
    #filetypes to be filtered
    filetypes = set(filetype for filetype in ['mng', 'pct', 'bmp', 'gif', 'jpg', 'jpeg', 'png', 'pst', 'psp', 'tif', 'tiff', 'ai', 'drw', 'dxf', 'eps', 'ps', 'svg',
                'mp3', 'wma', 'ogg', 'wav', 'ra', 'aac', 'mid', 'au', 'aiff',
                '3gp', 'asf', 'asx', 'avi', 'mov', 'mp4', 'mpg', 'qt', 'rm', 'swf', 'wmv', 'm4a',
                'css', 'pdf', 'doc', 'exe', 'bin', 'rss', 'zip', 'rar', 'msu', 'flv', 'dmg',
                'mng?download=true', 'pct?download=true', 'bmp?download=true', 'gif?download=true', 'jpg?download=true', 'jpeg?download=true', 'png?download=true', 'pst?download=true', 'psp?download=true', 'tif?download=true', 'tiff?download=true', 'ai?download=true', 'drw?download=true', 'dxf?download=true', 'eps?download=true', 'ps?download=true', 'svg?download=true',
                'mp3?download=true', 'wma?download=true', 'ogg?download=true', 'wav?download=true', 'ra?download=true', 'aac?download=true', 'mid?download=true', 'au?download=true', 'aiff?download=true',
                '3gp?download=true', 'asf?download=true', 'asx?download=true', 'avi?download=true', 'mov?download=true', 'mp4?download=true', 'mpg?download=true', 'qt?download=true', 'rm?download=true', 'swf?download=true', 'wmv?download=true', 'm4a?download=true',
                'css?download=true', 'pdf?download=true', 'doc?download=true', 'exe?download=true', 'bin?download=true', 'rss?download=true', 'zip?download=true', 'rar?download=true', 'msu?download=true', 'flv?download=true', 'dmg?download=true'])

    #function to refresh the allowed domain list after adding domains
    def refreshAllowedDomains(self):
        for mw in self.crawler.engine.scraper.spidermw.middlewares:
            if isinstance(mw, scrapy.spidermiddlewares.offsite.OffsiteMiddleware):
                mw.spider_opened(self)
           
    #function which extracts the subdomain from a url string or response object
    def subdomainGetter(self, response):
        #if string
        if isinstance(response, str):
            tld = tldextract.extract(response)
            if tld.subdomain != "":
                domain = tld.subdomain + "." + tld.registered_domain
                return domain
            else:
                domain = tld.registered_domain
                return domain            
        #if scrapy response object
        else:
            tld = tldextract.extract(response.url)
            if tld.subdomain != "":
                domain = tld.subdomain + "." + tld.registered_domain
                return domain
            else:
                domain = tld.registered_domain
                return domain
        
    #function which checks if there has been a redirect from the starting url
    def checkRedirectDomain(self, response):
        return tldextract.extract(response.url).registered_domain != tldextract.extract(response.request.meta.get("download_slot")).registered_domain
    
    #function which extracts text using tags
    def extractText(self, response):
        text = []
        text.append(["p", [" ".join(response.xpath("//p/text()").extract())]])
        text.append(["div", [" ".join(response.xpath("//div/text()").extract())]])
        text.append(["tr", [" ".join(response.xpath("//tr/text()").extract())]])
        text.append(["td", [" ".join(response.xpath("//td/text()").extract())]])
        text.append(["font", [" ".join(response.xpath("//font/text()").extract())]])
        text.append(["li", [" ".join(response.xpath("//li/text()").extract())]])
        text.append(["small", [" ".join(response.xpath("//small/text()").extract())]])
        text.append(["strong", [" ".join(response.xpath("//strong/text()").extract())]])
        text.append(["h1", [" ".join(response.xpath("//h1/text()").extract())]])
        text.append(["h2", [" ".join(response.xpath("//h2/text()").extract())]])
        text.append(["h3", [" ".join(response.xpath("//h3/text()").extract())]])
        text.append(["h4", [" ".join(response.xpath("//h4/text()").extract())]])
        text.append(["h5", [" ".join(response.xpath("//h5/text()").extract())]])
        text.append(["h6", [" ".join(response.xpath("//h6/text()").extract())]])
        text.append(["span", [" ".join(response.xpath("//span/text()").extract())]])
        text.append(["b", [" ".join(response.xpath("//b/text()").extract())]])
        text.append(["em", [" ".join(response.xpath("//em/text()").extract())]])
        
        return text
    
    #function which reorders the urlstack, giving highest priority to short urls and language tagged urls
    def reorderUrlstack(self, urlstack, language, prefer_short_urls):
       preferred_language = []
       other_language = []
       language_tags = []
       if language == "":
           preferred_language = urlstack
       else:
           for ISO in language:
               language_tags.append("/{}/".format(ISO))
               language_tags.append("/{}-{}/".format(ISO, ISO))
               language_tags.append("?lang={}".format(ISO))
           for url in urlstack:
               if any(tag in url for tag in language_tags):
                   preferred_language.append(url)
               else:
                   other_language.append(url)
       if prefer_short_urls == "on":
           urlstack = sorted(preferred_language, key=len) + sorted(other_language, key=len)
       else:
           urlstack = preferred_language + other_language
       return urlstack        
   
   
##################################################################
# START REQUEST
##################################################################
    
    #start request and add ID to meta
    def start_requests(self):
        i = -1
        for url in self.start_urls:
            i += 1
            ID = self.IDs[i]
            yield scrapy.Request(url, meta={"ID": ID}, dont_filter=True, callback=self.parse, errback=self.errorback)
  
    #errorback creates an collector item, records the error type, and passes it to the pipeline   
    def errorback(self, failure):
        loader = ItemLoader(item=Collector())
        if failure.check(HttpError):
            response = failure.value.response
            loader.add_value("dl_slot", response.request.meta.get('download_slot'))
            loader.add_value("start_page", "")
            loader.add_value("scraped_urls", "")
            loader.add_value("redirect", [None])
            loader.add_value("scraped_text", "")
            loader.add_value("error", response.status)
            loader.add_value("ID", response.request.meta["ID"])
            yield loader.load_item()
        elif failure.check(DNSLookupError):
            request = failure.request
            loader.add_value("dl_slot", request.meta.get('download_slot'))
            loader.add_value("start_page", "")
            loader.add_value("scraped_urls", "")
            loader.add_value("redirect", [None])
            loader.add_value("scraped_text", "")
            loader.add_value("error", "DNS")
            loader.add_value("ID", request.meta["ID"])
            yield loader.load_item()
        elif failure.check(TimeoutError, TCPTimedOutError):
            request = failure.request
            loader.add_value("dl_slot", request.meta.get('download_slot'))
            loader.add_value("start_page", "")
            loader.add_value("scraped_urls", "")
            loader.add_value("redirect", [None])
            loader.add_value("scraped_text", "")
            loader.add_value("error", "Timeout")
            loader.add_value("ID", request.meta["ID"])
            yield loader.load_item()
        else:
            request = failure.request
            loader.add_value("dl_slot", request.meta.get('download_slot'))
            loader.add_value("start_page", "")
            loader.add_value("scraped_urls", "")
            loader.add_value("redirect", [None])
            loader.add_value("scraped_text", "")
            loader.add_value("error", "other")
            loader.add_value("ID", request.meta["ID"])
            yield loader.load_item()


##################################################################
# MAIN PARSE
##################################################################
      
    def parse(self, response):
        #initialize collector item which stores the website's content and meta data
        loader = ItemLoader(item=Collector())
        loader.add_value("dl_slot", response.request.meta.get('download_slot'))
        loader.add_value("redirect", self.checkRedirectDomain(response))
        loader.add_value("start_page", response.url)
        loader.add_value("start_domain", self.subdomainGetter(response))  
        loader.add_value("scraped_urls", [response.urljoin(response.url)])
        loader.add_value("scrape_counter", 1)
        loader.add_value("scraped_text", [self.extractText(response)])
        loader.add_value("error", "None")
        loader.add_value("ID", response.request.meta["ID"])

        #initialize the fingerprints set which stores all fingerprints of visited websites
        fingerprints = set()
        #add the fingerprints of the start_page
        fingerprints.add(request_fingerprint(response.request))
        
        #if there was an initial redirect, the new domain is added to the allowed domains
        domain = self.subdomainGetter(response)
        if domain not in self.allowed_domains:
            self.allowed_domains.append(domain)
            self.refreshAllowedDomains()

        #extract all urls from the page...
        urls = response.xpath("//a/@href").extract() + response.xpath("//frame/@src").extract() + response.xpath("//frameset/@src").extract()
        #...and safe them to a urlstack
        urlstack = [response.urljoin(url) for url in urls]

        response.meta["urlstack"] = urlstack
        response.meta["loader"] = loader
        response.meta["fingerprints"] = fingerprints

        #make a request for the same url in the web archiv
        original_datestack = self.date.split(",")
        current_datestack = original_datestack

        date = current_datestack.pop(0)
        archiveurl = 'https://web.archive.org/web/' + date + 'id_/' + response.url

        # get redirected URL
        r = requests.get(archiveurl)
        redirected = r.url
        yield scrapy.Request(redirected, meta={"loader": loader, "urlstack": urlstack, "current_datestack": current_datestack, "original_datestack": original_datestack, "current_url": archiveurl, "fingerprints": fingerprints, "handle_httpstatus_list" : [302], 'dont_redirect': True}, dont_filter=True, callback=self.parse_archive_subpage, errback=self.processURLstack)
    

    
##################################################################
# PARSE SUB PAGE
##################################################################
    
    def parse_subpage(self, response):
        #check again
        if request_fingerprint(response.request) in response.meta["fingerprints"]:
            return self.processURLstack(response)
       
        
        #save the fingerprint to mark the page as read
        response.meta["fingerprints"].add(request_fingerprint(response.request))
        
        # #opt out and fall back to processURLstack
        # #if http client errors
        # if response.status > 308:
        #     print("308")
        #     return self.processURLstack(response)
    
        # #if redirect sent us to an non-allowed domain
        # elif self.subdomainGetter(response) not in self.allowed_domains:
        #     print("Not allowed domain")
        #     return self.processURLstack(response)
        
        # #skip broken urls
        # if response.status == 301:      
        #     print("301")                   
        #     #revive the loader from the response meta data
        #     loader = response.meta["loader"]
            
        #     #check whether this request was redirected to an allowed url which is actually another firm
        #     if loader.get_collected_values("start_domain")[0] != self.subdomainGetter(response):
        #         raise ValueError()

        #     #extract urls and add them to the urlstack
        #     urls = response.xpath("//a/@href").extract() + response.xpath("//frame/@src").extract() + response.xpath("//frameset/@src").extract()
        #     for url in urls:
        #         response.meta["urlstack"].append(response.urljoin(url))
                                    
        #     #pass back the updated urlstack    
        #     return self.processURLstack(response)
        
        # if response.status == 302:           
        #     print("302")             
        #     #revive the loader from the response meta data
        #     loader = response.meta["loader"]
            
        #     #check whether this request was redirected to a allowed url which is actually another firm
        #     if loader.get_collected_values("start_domain")[0] != self.subdomainGetter(response):
        #         raise ValueError()

        #     #extract urls and add them to the urlstack
        #     urls = response.xpath("//a/@href").extract() + response.xpath("//frame/@src").extract() + response.xpath("//frameset/@src").extract()
        #     for url in urls:
        #         response.meta["urlstack"].append(response.urljoin(url))
                                    
        #     #pass back the updated urlstack    
        #     return self.processURLstack(response)

        
        #revive the loader from the response meta data
        loader = response.meta["loader"]
        
        #check whether this request was redirected to an allowed url which is actually another firm
        if loader.get_collected_values("start_domain")[0] != self.subdomainGetter(response):
            raise ValueError()

        #extract urls and add them to the urlstack
        # urls = response.xpath("//a/@href").extract() + response.xpath("//frame/@src").extract() + response.xpath("//frameset/@src").extract()
        # for url in urls:
        #     response.meta["urlstack"].append(response.urljoin(url))
                
        # #add info to collector item
        loader.replace_value("scrape_counter", loader.get_collected_values("scrape_counter")[0]+1)
        loader.add_value("scraped_urls", [response.urljoin(response.url)])
        loader.add_value("scraped_text", [self.extractText(response)])

        # #extract all urls from the page...
        # urls = response.xpath("//a/@href").extract() + response.xpath("//frame/@src").extract() + response.xpath("//frameset/@src").extract()
        # #...and safe them to a urlstack
        # urlstack = [response.urljoin(url) for url in urls]

        #make a request for the subpages in the web archive
        current_datestack = self.date.split(",")
        date = current_datestack.pop(0)

        urlstack = response.meta["urlstack"]

        archiveurl = 'https://web.archive.org/web/' + date + 'id_/' + response.url
        # get redirected URL
        r = requests.get(archiveurl)
        redirected = r.url

        yield scrapy.Request(redirected, meta={"loader": loader, "urlstack": urlstack, "current_datestack": current_datestack, "original_datestack": response.meta["original_datestack"], "current_url": archiveurl, "fingerprints": response.meta["fingerprints"], "handle_httpstatus_list" : [302], 'dont_redirect': True}, dont_filter=True, callback=self.parse_archive_subpage, errback=self.processURLstack)

    

##################################################################
# PARSE WEB ARCHIVE PAGE
##################################################################
    #repeat the parse subpage function for the webarchive urls
    def parse_archive_subpage(self, response):
        #check again
        if request_fingerprint(response.request) in response.meta["fingerprints"]:
            return self.processURLstack(response)
    
        #save the fingerprint to mark the page as read
        response.meta["fingerprints"].add(request_fingerprint(response.request))

        #revive the loader from the response meta data
        loader = response.meta["loader"]

        #add info to collector item
        loader.add_value("scraped_urls", [response.urljoin(response.url)])
        loader.add_value("scraped_text", [self.extractText(response)])

        #if there are still unused dates in the datestack, request the current subpage with this date from the archive
        current_datestack = response.meta["current_datestack"]
        if len(current_datestack) > 0:
            date = current_datestack.pop(0)

            ### splicing necessary as the response current_url is "incorrect" 
            archiveurl = 'https://web.archive.org/web/' + date + 'id_/' + response.meta["current_url"][40:]

            # get redirected URL
            r = requests.get(archiveurl)
            redirected = r.url
            yield scrapy.Request(redirected, meta={"loader": loader, "urlstack": response.meta["urlstack"], "current_datestack": current_datestack, "original_datestack": response.meta["original_datestack"], "current_url": archiveurl,  "fingerprints": response.meta["fingerprints"], "handle_httpstatus_list" : [302], 'dont_redirect': True}, dont_filter=True, callback=self.parse_archive_subpage, errback=self.processURLstack)

        #if there are no more dates in the datestack, return to the URL stack to process the next subpage
        else:
            ### make an "empty" request to bypass error
            yield scrapy.Request(response.url, meta={"loader": loader, "urlstack": response.meta["urlstack"], "current_datestack": current_datestack, "original_datestack": response.meta["original_datestack"], "fingerprints": response.meta["fingerprints"], "handle_httpstatus_list" : [302], 'dont_redirect': True}, dont_filter=True, callback=self.processURLstack, errback=self.processURLstack)

			
##################################################################
# PROCESS URL STACK
##################################################################
         
    def processURLstack(self, response):
        #get meta data from response object to revive dragged stuff
        meta = response.request.meta
        loader = meta["loader"]
        urlstack = meta["urlstack"]
        fingerprints = meta["fingerprints"]
        
        #check whether max number of websites has been scraped for this website
        if loader.get_collected_values("scrape_counter")[0] >= self.site_limit:
            del urlstack[:]
        
        #reorder the urlstack to scrape the most relevant urls first
        urlstack = self.reorderUrlstack(urlstack, self.language, self.prefer_short_urls)
            
        #check if the next url in the urlstack is valid
        while len(urlstack) > 0:
            #pop non-valid domains
            domain = self.subdomainGetter(urlstack[0])
            if domain not in self.allowed_domains:
                urlstack.pop(0)
            #pop "mailto" urls
            elif re.match(r"mailto", urlstack[0]):
                urlstack.pop(0)
            #pop unwanted filetypes
            elif urlstack[0].split(".")[-1].lower() in self.filetypes:
                urlstack.pop(0)
            #pop visited urls 
            #(potential bottleneck: Request has to be sent to generate fingerprint from)
            elif request_fingerprint(scrapy.Request(urlstack[0], callback=None)) in fingerprints:
                urlstack.pop(0)
            else:
                break

        #if the url was assessed to be valid, send out a request and callback the parse_archive function
        #errbacks return to processURLstack
        #ALLOW ALL HTTP STATUS: 
        #errors must be caught in the callback function, because middleware caught request break the sequence and collector items get lost
        if len(urlstack) > 0:
            
            original_datestack = meta["original_datestack"]

            url = urlstack.pop(0)
            #make request for the current website
            yield scrapy.Request(url, meta={"loader": loader, "urlstack": urlstack, "fingerprints": fingerprints, "original_datestack": original_datestack,'handle_httpstatus_all': True, 'current_url': url}, dont_filter=True, callback=self.parse_subpage, errback=self.processURLstack)


        #if there are no urls left in the urlstack, the website was scraped completely and the item can be sent to the pipeline
        else:
            yield loader.load_item()
    