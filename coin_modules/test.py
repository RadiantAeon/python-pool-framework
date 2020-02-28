import json
import logging
import asyncio
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

class TCPServer(asyncio.Protocol):
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.log.info('Connection from {}'.format(peername))
        #self.transport = transport
        self.active_transports.append(transport)

    def data_received(self, data):
        message = data.decode()
        self.log.debug('Data received: {!r}'.format(message))
        
        
        message = self.stratumHandling.handleMessage(self, message)
        
        self.log.debug('Send: {!r}'.format(message))
        self.transport.write(data)

        self.log.debug('Close the client socket')
        self.transport.close()

class StratumHandling():
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
            "mining.suggest_target": self.mining.suggest_target,
            "daemon.blocknotify": self.daemon.blocknotify
        }
        
        # generic stratum protocol response
        template = {"error": None, "id": 0, "result": True}
        
        # check for valid json and if it isn't valid cyberbully the sender
        try:
            message_parsed = json.loads(message)
        except:
            response = template
            response["error"] = "ur mom"
            response["result"] = "no this is not json"
        
        # otherwise send the message to the correct method
        else:
            try:
                response = methods[message_parsed["method"]](self, message_parsed, template)
            except:
                response = template
                response["error"] = "Invalid method!"
        return(json.dumps(response).encode("utf-8"))
        
class Mining():
        def authorize(self, message, template):
            params = message["params"]
            # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
            if self.mongodb_connection.find_one({"user": params[0], "password": params[1]}) != None:
                template["result"] = True
            else:
                template["result"] = False
                template["error"] = "Unauthorized"
            return template

class Daemon():
    def blocknotify(self, message, template):
        for transport in self.active_transports:


class Client():

class Main():
    def __init__(self, config, global_config, mongodb_connection, log):
        # this makes it hella easier to access variables such as active_tranports and gets rid of the shit ton of args passed to everything - i love oop
        self.log = log
        self.mongodb_connection = mongodb_connection
        self.rpc_connection = rpc_connection
        self.stratumHandling = StratumHandling()
        self.mining = self.Mining()
        self.daemon = self.Daemon()
        self.tcpserver = self.TCPServer()
        self.active_transports = []
        self.main()
    async def main(self):
        #connects to bitcoin daemon with settings from config
        rpc_connection = AuthServiceProxy("http://%s:%s@%s:%s"%(self.config['daemon']["rpc_username"], self.config['daemon']["rpc_password"], self.config['daemon']["daemon_ip"], self.config['daemon']["daemon_port"]))
        loop = asyncio.get_running_loop()
        
        # pro tip - the config passed to it is the coin specific one and the self.config is the global config
        server = await loop.create_server(
            # initializes tcp server on ip and port defined in config
            lambda: self.tcpserver(self),
            self.global_config['ip'], self.config['port'])

        async with server:
            await server.serve_forever()
