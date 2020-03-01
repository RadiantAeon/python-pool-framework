import json
import logging
import socket
import threading
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

class TCPServer(object):
    """def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.log.info('Connection from {}'.format(peername))
        #self.transport = transport
        # add transports to the active_transports dictionary with the transport stored in a dictionary
        self.transport_num += 1
        self.active_transports[str(self.transport_num)] = {"transport": transport}

    def data_received(self, data):
        message = data.decode()
        self.log.debug('Data received: {!r}'.format(message))


        message = self.stratumHandling.handle_message(self, message)

        self.log.debug('Send: {!r}'.format(message))
        self.transport.write(data)

        self.log.debug('Close the client socket')
        self.transport.close()"""
    def __init__(self, config, global_config, mongodb_connection, log):
        # this makes it hella easier to access variables such as active_tranports and gets rid of the shit ton of args passed to everything - i love oop
        self.log = log
        self.mongodb_connection = mongodb_connection
        self.stratumHandling = StratumHandling()
        self.mining = self.Mining()
        self.daemon = self.Daemon()
        self.client = self.Client()
        self.clients = {}
        self.transport_num = 0
        self.config = config
        self.global_config = global_config
        # connects to bitcoin daemon with settings from config
        self.rpc_connection = AuthServiceProxy("http://%s:%s@%s:%s"%(self.config['daemon']["rpc_username"], self.config['daemon']["rpc_password"], self.config['daemon']["daemon_ip"], self.config['daemon']["daemon_port"]))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.global_config['ip'], self.config['port']))

    def listen(self):
        self.sock.listen(5)
        while True:
            client, address = self.sock.accept()
            client.settimeout(300)
            threading.Thread(target = self.stratumHandling.listen,args = (client,address)).start()

class StratumHandling():
    def listen(self, client, address):
        size = 1024
        while True:
            try:
                data = client.recv(size)
                if data:
                    # Set the response to echo back the received data
                    response = self.handle_message(data)
                    client.send(response)
                else:
                    self.log.debug("Client " + str(address) + " disconnected")
                    raise Exception("Client disconnected")
            except:
                client.close()
                return False

    def handle_message(self, message):
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
        template = self.config['stratum']['template']
        
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
        
class Mining:
        def authorize(self, message, template):
            params = message["params"]
            # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
            if self.mongodb_connection.find_one({"user": params[0], "password": params[1]}) != None:
                template["result"] = True
            else:
                template["result"] = False
                template["error"] = "Unauthorized"
            return template

class Daemon:
    def blocknotify(self, message, template):
        response = template

        response['method'] = "mining.notify"

        for transport in self.active_transports:
            transport.write(response)

class Client:
