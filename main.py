import os
import json
import logging
import importlib
import ssl
import asyncio
import aiozmq
import zmq
from jsonrpcserver import method, async_dispatch as dispatch
import json
from pymongo import MongoClient

# initialize logger
logging.basicConfig(format="%(asctime)s %(levelname)s:%(module)s: %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

class poolFramework:
    def __init__(self):
        self.config = json.loads(open("config.json","r").read())
        # load ssl certs if defined in config
        if self.config['ssl_keyfile_path'] != "" and self['config.ssl_certfile_path'] != "":
           self.ssl_context = loadSSL()
        else:
           self.ssl_context = None
        self.coin_modules = {}
        self.coin_configs = []
        # connect to mongodb
        try:
            self.mongodb_connection = MongoClient(self.config["mongodb_connection_string"])
        except:
            log.error("Mongodb connection failed")
            quit()
        self.startup()
    
    def startup(self):

        directory = os.fsencode(self.config['coin_config_dir'])

        # load configs in config directory
        for filename in os.listdir(directory):
            filename = os.fsdecode(filename)
            if filename.endswith(".json"):
                # checks if the path in config contains a / on the end or not
                if self.config['coin_config_dir'].endswith("/"):
                    curr_config = json.loads(open(self.config['coin_config_dir'] + filename,"r").read())
                else:
                    curr_config = json.loads(open(self.config['coin_config_dir'] + "/" + filename,"r").read())
                
                # only load the config if the file name is the same as the coin name and the script file exsists
                if curr_config['coin'] == filename.replace(".json", "") and os.path.isfile(self.config['coin_modules_dir'] + curr_config['coin'] + ".py"):
                    self.coin_configs.append(curr_config)
                    spec = importlib.util.spec_from_file_location(curr_config['coin'], self.config['coin_modules_dir'] + curr_config['coin'] + ".py")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    self.coin_modules[curr_config['coin']] = module

                    log.info("Added coin module '%s' to modules list", curr_config['coin'])
                elif curr_config['coin'] == filename.replace(".json", "") and os.path.isfile(self.config['coin_modules_dir'] + "/" + curr_config['coin'] + ".py"):
                    self.coin_configs.append(curr_config)
                    spec = importlib.util.spec_from_file_location(curr_config['coin'], self.config['coin_modules_dir'] + curr_config['coin'] + ".py")
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    self.coin_modules[curr_config['coin']] = module

                    log.info("Added coin module '%s' to modules list", curr_config['coin'])
            else:
                continue

        # check for duplicate ports
        
        ports = []
        for config in self.coin_configs:
            if config['port'] in ports:
                log.error(str(config['coin']) + " has the same port configured as another coin!")
                quit
            else:
                ports.append(config['port'])

        for config in self.coin_configs:
            log.info("Initialized " + str(config['coin']) + " stratum")
            #main(self.config, config, log, self.ssl_context)
            curr_logger = logging.basicConfig(format="%(asctime)s " + config['coin'] + ": %(message)s", level=logging.INFO)
            # send the coin specific config, the global config, the mongodb connection for the collection that it is running on, and the logger
            asyncio.run(self.coin_modules[config['coin']].main(config, self.config, self.mongodb_connection[config.coin]), curr_logger)

    def loadSSL(self):
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.options |= (
            ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
        )
        ssl_context.set_ciphers("ECDHE+AESGCM")
        ssl_context.load_cert_chain(certfile=self['config.ssl_cert_path'], keyfile=self['config.ssl_keyfile_path'])
        ssl_context.set_alpn_protocols(["h2"])

poolFramework()
