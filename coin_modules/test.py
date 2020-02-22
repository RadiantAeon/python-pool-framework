import json
import logging
import asyncio

class TCPServer(asyncio.Protocol):
    def __init__(self, mongodb_connection):
        logging.basicConfig(format="%(asctime)s %(levelname)s:%(module)s: %(message)s", level=logging.INFO)
        self.log = logging.getLogger(__name__)
        self.mongodb_connection = mongodb_connection
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.log.info('Connection from {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        self.log.debug('Data received: {!r}'.format(message))
        
        message = StratumHandling.handleMessage(message, mongodb_connection)
        
        self.log.debug('Send: {!r}'.format(message))
        self.transport.write(data)

        self.log.debug('Close the client socket')
        self.transport.close()

class StratumHandling():
    def __init__(self, mongodb_connection):
        self.mongodb_connection = mongodb_connection
        self.mining = self.Mining()
    
    def handleMessage(self, message):
        # set up switch statement using dictionary containing all the stratum methods as detailed in https://en.bitcoin.it/wiki/Stratum_mining_protocol
        methods = {
            "mining.authorize": self.mining.authorize,
            "mining.capabilities": self.mining.capabilities,
            "mining.extranonce.subscribe": self.mining.extranonce_subscribe,
            "mining.get_transactions": self.mining.get_transactions,
            "mining.submit": self.mining.submit,
            "mining.subscribe": self.mining.subscribe,
            "mining.suggest_difficulty": self.mining.suggest_difficulty,
            "mining.suggest_target": self.suggest_target
        }
        
        # generic stratum protocol response
        template = {"error": None, "id": 0, "result": True}
        
        try:
            message_parsed = json.loads(message)
        except:
            response = template
            response["error"] = "ur mom"
            response["result"] = "no this is not json"
        else:
            try:
                response = methods[message_parsed["method"]](message_parsed, template, self.mongodb_connection)
            except:
                response = template
                response["error"] = "Invalid method!"
        return(json.dumps(response).encode("utf-8"))
        
class Mining():
        def authorize(self, message, template, mongodb_connection):
            params = message["params"]
            # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
            if mongodb_connection.find_one({"user": params[0], "password": params[1]}) != None:
                template["result"] = True
            else:
                template["result"] = False
                template["error"] = "Unauthorized"
            return template

        
async def main(config, global_config, mongodb_connection):
    loop = asyncio.get_running_loop()
        
    # pro tip - the config passed to it is the coin specific one and the self.config is the global config
    server = await loop.create_server(
        lambda: TCPServer(mongodb_connection),
        global_config['ip'], config['port'])

    async with server:
        await server.serve_forever()
