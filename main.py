import requests
import json
import logging
import time, datetime
import pandas

from enum import Enum

Currency = Enum('Currency', 'EUR USD')
Cryptomoney = Enum('Cryptomoney', 'BTC ETH')
Price = Enum('Price', 'buy sell spot')
Environment = Enum('Environment', 'TEST PROD')

#ENV = Environment.TEST
ENV = Environment.PROD

def create_logger(file = 'activity.log', level = logging.DEBUG):
    logger = logging.getLogger()
    logger.setLevel(level)
    # Define logging format
    formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')
    # Create the file handler
    file_handler = logging.handlers.RotatingFileHandler(file, 'a', 1000000, 1)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    # Create the stream handler
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    logger.addHandler(stream_handler)
    return logger
    
LOGGER = create_logger()

def get_current_timestamp():
    return datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')

if ENV == Environment.TEST:
    get_current_timestamp()

def initialize_files(logger=None):
    if logger != None:
        logger.warning("Erasing and Reinitializing all CSVs")
    for cmy in [c.name for c in Cryptomoney]:
        for ccy in [c.name for c in Currency]:
            f = open('data/{}-{}.csv'.format(cmy, ccy), 'w')
            f.write('time,' + ','.join([p.name for p in Price]) + '\n')
            f.close()

if ENV == Environment.TEST:
    initialize_files(LOGGER)

def get_value(cmy = Cryptomoney.BTC, ccy = Currency.EUR, prc = Price.spot):
    url = 'https://api.coinbase.com/v2/prices/{}-{}/{}'.format(cmy.name, ccy.name, prc.name)
    xhr = requests.get(url)
    if xhr.status_code != 200:
        raise Exception('XHR status '+str(xhr.status_code)+': '+xhr.reason+' ('+xhr.url+')')
    response = xhr.json()
    return float(response['data']['amount'])

if ENV == Environment.TEST:
    get_value()

def get_all_values(cmy = Cryptomoney.BTC, ccy = Currency.EUR):
    results = {}
    for p in Price:
        results[p.name] = get_value(cmy, ccy, p)
    return results

if ENV == Environment.TEST:
    get_all_values()

def add_line(logger = None):
    for cmy in Cryptomoney:
        for ccy in Currency:
            ts = get_current_timestamp()
            if logger != None:
                logger.info(ts + " - Getting all values.")
            all_values = get_all_values(cmy, ccy)
            f = open('data/{}-{}.csv'.format(cmy.name, ccy.name), 'a')
            f.write(ts + ',' + ','.join([str(all_values[p.name]) for p in Price]) + '\n')
            f.close()

if ENV == Environment.TEST:
    add_line(LOGGER)

def analyze_file(cmy = Cryptomoney.BTC, ccy = Currency.EUR):
    data = pandas.read_csv("data/{}-{}.csv".format(cmy.name, ccy.name), index_col=0)
    if data.index.size < 5:
        return 0
    rmean = data["spot"].rolling(5).mean()[-1]
    rstd = data["spot"].rolling(5).std()[-1]
    if data["buy"][-1] < rmean - 2 * rstd:
        return 1
    elif data["sell"][-1] > rmean + 2 * rstd:
        return -1
    return 0

if ENV == Environment.TEST:
    analyze_file()

def analyze_data(ccy = Currency.EUR, logger = None):
    if logger != None:
        logger.info("Beginning analyze")
    results = {}
    for cmy in Cryptomoney:
        action = analyze_file(cmy, ccy)
        results[cmy.name] = action
        # Log every action to take
        if action == 1 and logger != None:
            logger.info("Action to take: BUY {}".format(cmy.name))
        if action == -1 and logger != None:
            logger.info("Action to take: SELL {}".format(cmy.name))
    return results

if ENV == Environment.TEST:
    analyze_data()

def initialize_simulation(ccy = Currency.EUR, logger = None):
    if logger != None:
        logger.warning("Erasing and Reinitializing simulation")
    wallet = json.dumps({
        'value':1000,
        'currency':ccy.name,
        'last_actions': dict((c.name, 0) for c in Cryptomoney),
        'last_prices': dict((c.name, get_value(c, ccy)) for c in Cryptomoney)
    })
    f = open('simulation.json', 'w')
    f.write(wallet)
    f.close()

if ENV == Environment.TEST:
    initialize_simulation(logger = LOGGER)

def simulate(analyze_results, ccy = Currency.EUR, logger = None):
    if logger != None:
        logger.info("Beginning simulation")
    wallet = json.load(open('simulation.json'))
    if logger != None and wallet["currency"] != ccy.name:
        logger.error("Currencies in simulation don't match")
        
    # Part 1 - Close previous actions
    for c in Cryptomoney:
        if wallet['last_actions'][c.name] == 1: # Close BUY action
            oldv = wallet['last_prices'][c.name]
            newv = get_value(c, ccy, Price.sell)
            res = 100 * newv / oldv
            wallet["value"] += res
            if logger != None:
                logger.info("Closing BUY deal: {} (old: {}, new: {})".format(res-100, oldv, newv))
        elif wallet['last_actions'][c.name] == -1: # Close SELL action
            oldv = wallet['last_prices'][c.name]
            newv = get_value(c, ccy, Price.buy)
            res = 100 * newv / oldv
            wallet["value"] -= res
            if logger != None:
                logger.info("Closing SELL deal: {} (old: {}, new: {})".format(100-res, oldv, newv))
                
    # Part 2 - Take new actions
    
    for c in Cryptomoney:
        if analyze_results[c.name] == 1: # Take BUY action
            wallet["value"] -= 100
            wallet["last_actions"][c.name] = 1
            wallet["last_prices"][c.name] = get_value(c, ccy, Price.buy)
        elif analyze_results[c.name] == -1: # Take SELL action
            wallet["value"] += 100
            wallet["last_actions"][c.name] = -1
            wallet["last_prices"][c.name] = get_value(c, ccy, Price.sell)
        else:
            wallet["last_actions"][c.name] = 0
    f = open('simulation.json', 'w')
    f.write(json.dumps(wallet))
    f.close()

if ENV == Environment.TEST:  
    simulate(analyze_data(logger = LOGGER), logger=LOGGER)

initialize_files(LOGGER)
add_line(logger=LOGGER)
analyze_results = analyze_data(logger=LOGGER)
simulate(analyze_results, logger=LOGGER)