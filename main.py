import os
import logging
import importlib
import ssl
import json
from pymongo import MongoClient

# initialize logger
logging.basicConfig(format="%(asctime)s %(levelname)s:%(module)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
config = json.loads(open("config.json","r").read())

# load ssl certs if defined in config
if config['ssl_keyfile_path'] != "" and config.['ssl_certfile_path'] != "":
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.options |= (
        ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
    )
    ssl_context.set_ciphers("ECDHE+AESGCM")
    ssl_context.load_cert_chain(certfile=config['ssl_keyfile_path'], keyfile=config.['ssl_certfile_path']h)
    ssl_context.set_alpn_protocols(["h2"])
else:
    ssl_context = None
    coin_modules = {}
    coin_configs = []

# connect to mongodb
try:
    mongodb_connection = MongoClient(config["mongodb_connection_string"])
except:
    log.error("Mongodb connection failed")
    quit()
# finish loading config and db stuff


directory = os.fsencode(config['coin_config_dir'])
# load configs in config directory
for filename in os.listdir(directory):
    filename = os.fsdecode(filename)
    if filename.endswith(".json"):
        # checks if the path in config contains a / on the end or not
        if config['coin_config_dir'].endswith("/"):
            curr_config = json.loads(open(config['coin_config_dir'] + filename,"r").read())
        else:
            curr_config = json.loads(open(config['coin_config_dir'] + "/" + filename,"r").read())
                
        # only load the config if the file name is the same as the coin name and the server python file exsists
        if curr_config['coin'] == filename.replace(".json", "") and os.path.isfile(config['coin_modules_dir'] + curr_config['coin'] + ".py"):
            coin_configs.append(curr_config)
            spec = importlib.util.spec_from_file_location(curr_config['coin'], config['coin_modules_dir'] + curr_config['coin'] + ".py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            coin_modules[curr_config['coin']] = module

            log.info("Added coin module '%s' to modules list", curr_config['coin'])
        # do the same thing but add a / on the end of the coin module directory because you never know
        elif curr_config['coin'] == filename.replace(".json", "") and os.path.isfile(config['coin_modules_dir'] + "/" + curr_config['coin'] + ".py"):
            coin_configs.append(curr_config)
            spec = importlib.util.spec_from_file_location(curr_config['coin'], config['coin_modules_dir'] + curr_config['coin'] + ".py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

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

for config in coin_configs:
    log.info("Initialized " + str(config['coin']) + " stratum")
    curr_logger = logging.getLogger(config['coin'])
    # send the coin specific config, the global config, the mongodb connection for the collection that it is running on, and the logger
    coin_modules[config['coin']].TCPServer(config, config, mongodb_connection[config['coin']], curr_logger)
