import json
import logging
import socket
import threading
import binascii
import hashlib
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
import socketserver

class StratumProtocol(TCPServer):
    def __init__(self, config, global_config, mongodb_connection, log):
        # this makes it hella easier to access variables such as active_tranports and gets rid of the shit ton of args passed to everything - i love oop
        self.log = log
        self.mongodb_connection = mongodb_connection
        self.clients = {}
        self.transport_num = 0
        self.config = config
        self.global_config = global_config
        # generic stratum protocol response
        self.response_template = self.config['stratum']['response_template']
        # this is just a variable to add onto so each thread can tell when there is a new block
        self.block_height = 0
        self.curr_job_id = 1
        self.job_template = [
            0, #  job_id - ID of the job. Use this ID while submitting share generated from this job.
            0, # prevhash - Initial part of coinbase transaction.
            0, # coinb1 - Initial part of coinbase transaction.
            0, # coinb2 - Final part of coinbase transaction.
            [], # merkle_branch - List of hashes, will be used for calculation of merkle root. This is not a list of all transactions, it only contains prepared hashes of steps of merkle tree algorithm.
            0, # version - Bitcoin block version.
            0, # nbits - Encoded current network difficulty
            0, # ntime - Current ntime/
            True, # clean_jobs - When true, server indicates that submitting shares from previous jobs don't have a sense and such shares will be rejected. When this flag is set, miner should also drop all previous jobs, so job_ids can be eventually rotated.
        ]
        # connects to bitcoin daemon with settings from config
        self.rpc_connection = AuthServiceProxy("http://%s:%s@%s:%s"%(self.config['daemon']["rpc_username"], self.config['daemon']["rpc_password"], self.config['daemon']["daemon_ip"], self.config['daemon']["daemon_port"]))
    
    '''def listen(self, client, address, job_id):
        size = 1024
        cached_block_height = []
        while True:
            try:
                data = client.recv(size)
                if data:
                    # send the message to the handler below
                    response = self.handle_message(data)
                    client.send(response)
                else:
                    self.log.debug("Client " + str(address) + " disconnected")
                    raise Exception("Client disconnected")
                if self.block_height != cached_block_height:
                    response = self.response_template
                    response['error'] =  None
                    job = self.curr_job
                    job[0] = job_id
                    response['params'] = self.curr_job
                    client.send(json.dumps(response))
            except:
                client.close()
                return False'''

    def handle_message(self, message):
        # set up switch statement using dictionary containing all the stratum methods as detailed in https://en.bitcoin.it/wiki/Stratum_mining_protocol
        methods = {
            "mining.authorize": self.authorize,
            "mining.capabilities": self.capabilities,
            "mining.extranonce.subscribe": self.extranonce_subscribe,
            "mining.get_transactions": self.get_transactions,
            "mining.submit": self.submit,
            "mining.subscribe": self.subscribe,
            "mining.suggest_difficulty": self.suggest_difficulty,
            "mining.suggest_target": self.suggest_target,
            "daemon.blocknotify": self.blocknotify # not part of stratum - notifications from daemon
        }
        
        # check for valid json and if it isn't valid cyberbully the sender
        try:
            message_parsed = json.loads(message)
        except:
            response = self.response_template
            response["error"] = "ur mom"
            response["result"] = "no this is not json"
        
        # otherwise send the message to the correct method
        else:
            try:
                response = methods[message_parsed["method"]](self, message_parsed)
            except:
                response = self.template
                response["error"] = "Invalid method!"
        return(json.dumps(response).encode("utf-8"))
    
    def authorize(self, message):
        params = message["params"]
        response = self.response_template
        # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
        if self.mongodb_connection.find_one({"user": params[0], "password": params[1]}):
            response["result"] = True
        else:
             response["result"] = False
             response["error"] = "Unauthorized"
        return response

    def blocknotify(self, message):
        # adds one to the block_num var which each thread checks for so we can broadcast new jobs
        curr_job = self.job_template
        try:
            blocktemplate = self.rpc_connection.getblocktemplate
            if blocktemplate["error"]:
                raise Exception("Failed getblocktemplate rpc call! Is the bitcoin daemeon open to rpc?")
            self.log.info("New block at height {}".format(blocktemplate["result"]["height"]))
        except Exception as error:
            self.log.error(error)
        self.curr_job[1] = blocktemplate["result"]["previousblockhash"]
        coinbase = binascii.a2b_hex(blocktemplate['coinbasetxn']['data'])
        extradata = b'yeet'
        original_length = ord(coinbase[41:42])
        curr_job[2] = coinbase[0:41] # first part of coinbase transaction
        curr_job[3] = coinbase[42:42 + original_length] + extradata + coinbase[42 + original_length:] # second part of coinbase transaction
        transaction_list = [coinbase] + [binascii.a2b_hex(a['data']) for a in blocktemplate["result"]["transactions"]]
        curr_job[4] = [hashlib.sha256(hashlib.sha256(transaction).digest()).digest() for transaction in transaction_list] # hash every transaction twice to make prepared merkle hashes
        curr_job[5] = blocktemplate["result"]["version"]
        curr_job[6] = blocktemplate["result"]["curtime"]
        self.curr_job = curr_job
        self.block_height = blocktemplate["result"]["height"]
        return

class TCPServer(socketserver.BaseRequestHandler):
    def handle(self):
        # self.request - TCP socket connected to the client
        self.data = self.request.recv(2048).strip()
        print("{} sent:".format(self.client_address[0]))
        print(self.data)
        response = StratumProtocol.handle_message(self.data.decode('utf-8'))
        # just send back ACK for data arrival confirmation
        self.request.sendall(response)

def init_server(config, global_config, mongodb_connection, log):
    socketserver.TCPServer((global_config['ip'], config['port']), TCPServer).serve_forever()
    return StratumProtocol(config, global_config, mongodb_connection, log)