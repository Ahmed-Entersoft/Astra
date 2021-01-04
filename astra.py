import argparse
import base64
import json
import requests
import time
import ast
import utils.logger as logger
import utils.logs as logs
import urllib.parse
import hashlib
import webbrowser
import re

from core.zapscan import *
from core.parsers import *
from utils.logger import *
from core.login import APILogin
from utils.logger import logger
from utils.config import update_value,get_value,get_allvalues
from modules.cors import cors_main
from modules.auth import auth_check
from modules.rate_limit import rate_limit
from modules.csrf import csrf_check
from modules.jwt_attack import jwt_check
from modules.sqli import sqli_check
from modules.xss import xss_check
from modules.redirect import open_redirect_check
from modules.xxe import xxe_scan
from modules.crlf import crlf_check
from modules.security_headers_missing import security_headers_missing
from core.zap_config import zap_start
from multiprocessing import Process
from utils.db import Database_update
from utils.email_cron import email_start_cron


if os.getcwd().split('/')[-1] != 'API':
    from API.api import main
    
dbupdate = Database_update()

def parse_collection(collection_name,collection_type):
    if collection_type == 'Postman':
        parse_data.postman_parser(collection_name)
    else:
        print("[-]Failed to Parse collection")
        sys.exit(1)

def scan_postman_collection(file_name,scanid,new_url=None):
    # Read and parse postman collection file
    try:
        parse_data = PostmanParser()
        parse_data.postman_parser(file_name)
        for data in parse_data.api_lst:
            try:
                url = data['url']['raw']
            except:
                url = data['url']
            headers,method,body = data['headers'],data['method'],''
            if headers:
                try:
                    headers = add_headers(headers)
                except:
                    pass

            if data['body'] != '':
                body = json.loads(base64.b64decode(data['body']))


            if new_url is not None and new_url is not "NA":
                uri = url[[m.start() for m in re.finditer('/',url)][2]:]
                new_url = new_url+uri
            else:
                new_url = url

            p = Process(target=modules_scan,args=(new_url,method,headers,body,scanid),name='module-scan')
            p.start()

        email_start_cron()
        return True
    
    except:
        return False


def scan_complete():
    print("[+]Scan has been completed")
    webbrowser.open("http://127.0.0.1:8094/reports.html#"+scanid)
    while True:
        pass

def generate_scanid():
    global scanid
    scanid = hashlib.md5(str(time.time()).encode('utf-8')).hexdigest()
    return scanid

def add_headers(headers):
    # This function deals with adding custom header and auth value .
    auth_type = get_value('config.property','login','auth_type')
    if auth_type == 'cookie':
        cookie = get_value('config.property','login','cookie')
        if cookie:
            cookie_dict = ast.literal_eval(cookie)
            cookie_header = {'Cookie': cookie_dict['cookie']}
            headers.update(cookie_header)
    else:
        auth_success = get_value('config.property','login','auth_success')
        if auth_success == 'Y':
            auth_success_token = get_value('config.property','login','auth_success_token')
            #auth_request_header = get_value('config.property','login','auth_request_token')
            auth_success_param = get_value('config.property','login','auth_success_param')
            auth_header = {auth_success_param : auth_success_token }
            headers.update(auth_header)

    try:
        custom_header = get_value('config.property','login','headers')
        custom_header = ast.literal_eval(custom_header)
        headers.update(custom_header)
    except:
        pass

    return headers

def read_scan_policy():
    try:
        scan_policy = get_value('scan.property','scan-policy','attack')
        attack = ast.literal_eval(scan_policy)

    except Exception as e:
        print(e)

    return attack

def update_scan_status(scanid, module_name=None, count=None):
    #Update scanning status and total scan of module into DB.
    time.sleep(3)
    if count is not None:
        dbupdate.update_scan_record({"scanid": scanid}, {"$set" : {"total_scan" : count}})
    else:
        dbupdate.update_scan_record({"scanid": scanid}, {"$set" : {module_name : "Y"}})


def modules_scan(url,method,headers,body,scanid=None):
    '''Scanning API using different engines '''
    attack = read_scan_policy()
    if attack is None:
        print("Failed to start scan.")
        sys.exit(1)

    if scanid is None:
        scanid = generate_scanid()
    
    count = 0
    for key,value in attack.items():
        if value == 'Y' or value =='y':
            count += 1

    update_scan_status(scanid,"",count)


    if attack['zap'] == "Y" or attack['zap'] == "y":
        api_scan = zap_scan()
        status = zap_start()
        if status is True:
            api_scan.start_scan(url,method,headers,body,scanid)

    # Custom modules scan
    if attack['cors'] == 'Y' or attack['cors'] == 'y':
        handleException(lambda: cors_main(url,method,headers,body,scanid), "CORS")
        update_scan_status(scanid, "cors")
    if attack['Broken auth'] == 'Y' or attack['Broken auth'] == 'y':
        handleException(lambda: auth_check(url,method,headers,body,scanid), "Authentication")
        update_scan_status(scanid, "auth")
    if attack['Rate limit'] == 'Y' or attack['Rate limit'] == 'y':
        handleException(lambda: rate_limit(url,method,headers,body,scanid), "Rate limit")
        update_scan_status(scanid, "Rate limit")
    if attack['csrf'] == 'Y' or attack['csrf'] == 'y':
        handleException(lambda: csrf_check(url,method,headers,body,scanid), "CSRf")
        update_scan_status(scanid, "csrf")
    if attack['jwt'] == 'Y' or attack['jwt'] == 'y':
        handleException(lambda: jwt_check(url,method,headers,body,scanid), "JWT")
        update_scan_status(scanid, "jwt")
    if attack['sqli'] == 'Y' or attack['sqli'] == 'y':
        handleException(lambda: sqli_check(url,method,headers,body,scanid), "SQL injection")
        update_scan_status(scanid, "sqli")
    if attack['xss'] == 'Y' or attack['xss'] == 'y':
        handleException(lambda: xss_check(url,method,headers,body,scanid), "XSS")
        update_scan_status(scanid, "xss")
    if attack['open-redirection'] == 'Y' or attack['open-redirection'] == 'y':
        handleException(lambda: open_redirect_check(url,method,headers,body,scanid), "Open redirect")
        update_scan_status(scanid, "open-redirection")
    if attack['xxe'] == 'Y' or attack['xxe'] == 'y':
        xxe = xxe_scan()
        handleException(lambda: xxe.xxe_test(url,method,headers,body,scanid), "XXE")
        update_scan_status(scanid, "xxe")
    if attack['crlf'] == 'Y' or attack['crlf'] == 'y':
        handleException(lambda: crlf_check(url,method,headers,body,scanid), "CRLF")
        update_scan_status(scanid, "crlf")
    if attack['security_headers'] == 'Y' or attack['security_headers'] == 'y':
        handleException(lambda: security_headers_missing(url,method,headers,body,scanid), "security_headers")
        update_scan_status(scanid, "security_headers") 

def handleException(method, module_name):
    try:
        #raise Exception("handle exception")
        method()
    except Exception:
        print("exception in", module_name)

def validate_data(url,method):
    ''' Validate HTTP request data and return boolean value'''
    validate_url = urllib.parse.urlparse(url)
    http_method = ['GET','POST','DEL','OPTIONS','PUT']
    if method in http_method and bool(validate_url.scheme) is True:
        validate_result = True
    else:
        validate_result = False

    return validate_result

def scan_single_api(url, method, headers, body, api, scanid=None):
    ''' This function deals with scanning a single API. '''
    if headers is None or headers == '':
            headers = {'Content-Type' : 'application/json'}

    try:
        # Convert header and body in dict format
        if type(headers) is not dict:
            headers = ast.literal_eval(headers)

        if body:
            if type(body) is not dict:
                body = ast.literal_eval(body)
    except:
        return False
    
    if method == '':
        method = 'GET'

    result = validate_data(url, method)
    if result is False:
        print ("[-]Invalid Arguments")
        return False

    if api == "Y":
        p = Process(target=modules_scan,args=(url,method,headers,body,scanid),name='module-scan')
        p.start()
        if api == "Y":
            return True
    else:
        modules_scan(url,method,headers,body,scanid)


def scan_core(collection_type,collection_name,url,headers,method,body,loginurl,loginheaders,logindata,login_require):
    ''' Scan API through different engines ''' 
    scanid = generate_scanid()
    if collection_type and collection_name is not None:
        parse_collection(collection_name,collection_type)
        if login_require is True:
            api_login.verify_login(parse_data.api_lst)

        for data in parse_data.api_lst:
            try:
                url = data['url']['raw']
            except:
                url = data['url']
            headers,method,body = data['headers'],data['method'],''
            if headers:
                try:
                    headers = add_headers(headers)
                except:
                    pass

            if data['body'] != '':
                body = json.loads(base64.b64decode(data['body']))

            modules_scan(url,method,headers,body,scanid)      

    else:
        print( "%s [-]Invalid Collection. Please recheck collection Type/Name %s" %(api_logger.G, api_logger.W))

def get_arg(args=None):
        parser = argparse.ArgumentParser(description='Astra - REST API Security testing Framework')
        parser.add_argument('-c', '--collection_type',
                            help='Type of API collection',
                            default='Postman')
        parser.add_argument('-n', '--collection_name',
                            help='Type of API collection')
        parser.add_argument('-u', '--url',
                            help='URL of target API')
        parser.add_argument('-headers', '--headers',
                            help='Custom headers.Example: {"token" : "123"}')
        parser.add_argument('-method', '--method',
                            help='HTTP request method',
                            default='GET',choices=('GET', 'POST', 'PUT','DELETE'))
        parser.add_argument('-b', '--body',
                            help='Request body of API')
        parser.add_argument('-l', '--loginurl',
                            help='URL of login API')
        parser.add_argument('-H', '--loginheaders',
                            help='Headers should be in a dictionary format. Example: {"accesstoken" : "axzvbqdadf"}')
        parser.add_argument('-d', '--logindata',
                            help='login data of API')
    

        results = parser.parse_args(args)
        if len(args) == 0:
            print ("%sAt least one argument is needed to procced.\nFor further information check help: %spython astra.py --help%s"% (api_logger.R, api_logger.G, api_logger.W))
            sys.exit(1)

        return (results.collection_type,
                results.collection_name,
                results.url,
                results.headers,
                results.method,
                results.body,
                results.loginurl,
                results.loginheaders,
                results.logindata,
                )

def main():
    collection_type,collection_name,url,headers,method,body,loginurl,loginheaders,logindata = get_arg(sys.argv[1:])
    if loginheaders is None:
            loginheaders = {'Content-Type' : 'application/json'}
    if collection_type and collection_name and loginurl and loginmethod and logindata:
        # Login data is given as an input. 
        api_login.fetch_logintoken(loginurl,loginmethod,loginheaders,logindata)
        login_require = False
    elif collection_type and collection_name and loginurl:
        # This will first find the given loginurl from collection and it will fetch auth token. 
        parse_collection(collection_name,collection_type)
        try:
            loginurl,lognheaders,loginmethod,logidata = api_login.parse_logindata(loginurl)
        except:
           print( "[-]%s Failed to detect login API from collection %s " %(api_logger.R, api_logger.W))
           sys.exit(1)
        api_login.fetch_logintoken(loginurl,loginmethod,loginheaders,logindata)
        login_require = False
    elif loginurl and loginmethod:
        api_login.fetch_logintoken(loginurl,loginmethod,loginheaders,logindata)
        login_require = False
    elif collection_type and collection_name and headers:
        #Custom headers
        update_value('login','header',headers)
        login_require = False
    elif url and collection_name and headers:
        #Custom headers
        update_value('login','header',headers)
        login_require = False
    elif url:
        if headers is None:
            headers = {'Content-Type' : 'application/json'}
        if method is None:
            method = "GET"
       
        login_require = False
    else:
        login_require = True

    if body:
        body = ast.literal_eval(body)

    # Configuring ZAP before starting a scan
    get_auth = get_value('config.property','login','auth_type')

    if collection_type and collection_name is not None:
        scan_core(collection_type,collection_name,url,headers,method,body,loginurl,loginheaders,logindata,login_require) 
    else:
        scanid = generate_scanid()
        scan_single_api(url, method, headers, body, "F", scanid)

    scan_complete()

if __name__ == '__main__':
    api_login = APILogin()
    parse_data = PostmanParser()
    api_logger = logger()
    api_logger.banner()
    main()
