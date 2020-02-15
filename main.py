import os
import json
import logging
import stratum
import importlib
import ssl

class poolFramework:
    def __init__(self):
        logging.basicConfig(format="%(levelname)s:%(module)s:%(message)s", level=logging.INFO)
        log = logging.getLogger(__name__)
        self.config = json.loads(open("config.json","r").read())
        if self.config.ssl_keyfile_path != "" and self.config.ssl_certfile_path != "":
            loadSSL()
        startup()
    def startup(self):

        pool_configs = []
        directory = os.fsencode(self.config.coin_config_dir)

        # load configs in config directory
        for filename in os.listdir(directory):
            filename = os.fsdecode(filename)
            if filename.endswith(".json"): 
                curr_config = json.loads(open(filename,"r").read())
                # only load the config if the file name is the same as the coin name
                if curr_config.coin_name == filename.replace("json", ""):
                    pool_configs.append(curr_config)
            else:
                continue

        # check for duplicate ports

        port = []
        for config in pool_configs:
            if config.port in ports:
                self.log.error(str(config.coin) + " has the same port configured as another coin!")
                quit
            else:
                ports.append(config.port)

        for config in pool_configs:
            stratum.Stratum(self.config, config, self.log, self.ssl_context)

    def loadSSL(self):
        self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.ssl_context.options |= (
            ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1 | ssl.OP_NO_COMPRESSION
        )
        self.ssl_context.set_ciphers("ECDHE+AESGCM")
        self.ssl_context.load_cert_chain(certfile=self.config.ssl_cert_path, keyfile=self.config.ssl_keyfile_path)
        self.ssl_context.set_alpn_protocols(["h2"])