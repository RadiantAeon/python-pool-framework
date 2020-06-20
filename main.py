import os
import logging
import importlib
import ssl
import json
from pymongo import MongoClient
import socketserver

# initialize logger
logging.basicConfig(format="%(asctime)s %(levelname)s:%(module)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
global_config = json.loads(open("config.json","r").read())
coin_modules = {}
coin_configs = []
coin_config_dir = 'coin_configs'
coin_modules_dir = 'coin_modules'

# connect to mongodb
try:
    mongodb_connection = MongoClient(global_config["mongodb_connection_string"])
except:
    log.error("Mongodb connection failed")
    quit()
# finish loading config and db stuff

directory = os.fsencode(coin_config_dir)
# load configs in config directory
for filename in os.listdir(directory):
    filename = os.fsdecode(filename)
    if filename.endswith(".json"):
        # open the current coin config
        curr_config = json.loads(open(coin_config_dir + "/" + filename, "r").read())

        # only load the coin if the file name is the same as the coin name and the corresponding python file exists
        if curr_config['coin'] == filename.replace(".json", "") and os.path.isfile(coin_modules_dir + '/' + curr_config['coin'] + ".py"):
            coin_configs.append(curr_config)
            module = importlib.import_module("{}.{}".format(coin_modules_dir, curr_config['coin']))
            coin_modules[curr_config['coin']] = module
            log.info("Added coin module '%s' to modules list", curr_config['coin'])
    else:
        continue

# check for duplicate ports
ports = []
for config in coin_configs:
    if config['port'] in ports:
        log.error(str(config['coin']) + " has the same port configured as another coin!")
        quit
    else:
        ports.append(config['port'])

stratumServers = []
for config in coin_configs:
    log.info("Initialized " + str(config['coin']) + " stratum")
    curr_logger = logging.getLogger(config['coin'])
    # send the coin specific config, the global config, the mongodb connection for the collection that it is running on, and the logger
    stratumServers.append(coin_modules[config['coin']].init_server(config, global_config, mongodb_connection, curr_logger))

while True:
    command = str(input()) # doesn't do anything yet