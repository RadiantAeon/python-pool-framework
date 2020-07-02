import json
import logging
import socket
import threading
import binascii
import hashlib
import multiprocessing
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor


class TCPServer(Protocol):
    def connectionMade(self):
        global curr_job_id
        curr_job_id += 1
        log.debug("New connection from {}".format(self.client_address))
        listen(self.request, self.client_address, curr_job_id)


def listen(client, address, job_id):
    global log
    global response_template
    global block_height
    global curr_job
    size = 1024
    cached_block_height = []
    recieve = multiprocessing.Process(target=client.recv, name="recieve", args=(size)) # socketserver doesn't let you use timeout https://stackoverflow.com/questions/15705948/python-socketserver-timeout
    while True:
        try:
            data = recieve.start()
            log.debug(data)
            if data:
                # send the message to the handler below
                response = handle_message(data, address)
                client.send(response)
            else:
                log.debug("Client " + str(address) + " disconnected")
                raise Exception("Client disconnected")
            if block_height != cached_block_height:
                response = response_template
                response['error'] =  None
                job = curr_job
                job[0] = job_id
                response['params'] = curr_job
                client.send(json.dumps(response))
        except:
            client.close()
            return False

def handle_message(message, address):
    global response_template
    global mongodb_connection
    global rpc_connection
    global log

    authorized = False # We don't need to read from the db every time to check

    def authorize():
        params = message["params"]
        response = response_template
        # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
        if mongodb_connection.find_one({"user": params[0], "password": params[1]}):
            response["result"] = True
            authorized = True
            log.debug("Authorized user {}".format(params[0]))
        else:
            response["result"] = False
            response["error"] = "Unauthorized"
            log.debug("Failed login by use {}".format(parmas[0]))
        return response

    # need to make it so blocknotify isn't attackable - currently anyone can call it to fuck with us
    def blocknotify():
        # adds one to the block_num var which each thread checks for so we can broadcast new jobs
        curr_job = job_template
        try:
            blocktemplate = rpc_connection.getblocktemplate
            if blocktemplate["error"]:
                raise Exception("Failed getblocktemplate rpc call! Is the bitcoin daemon running?")
            log.info("New block at height {}".format(blocktemplate["result"]["height"]))
        except Exception as error:
            log.error(error)
        curr_job[1] = blocktemplate["result"]["previousblockhash"]
        coinbase = binascii.a2b_hex(blocktemplate['coinbasetxn']['data'])
        extradata = b'yeet'
        original_length = ord(coinbase[41:42])
        curr_job[2] = coinbase[0:41]  # first part of coinbase transaction
        curr_job[3] = coinbase[42:42 + original_length] + extradata + coinbase[42 + original_length:]  # second part of coinbase transaction
        transaction_list = [coinbase] + [binascii.a2b_hex(a['data']) for a in blocktemplate["result"]["transactions"]]
        curr_job[4] = [hashlib.sha256(hashlib.sha256(transaction).digest()).digest() for transaction in transaction_list]  # hash every transaction twice to make prepared merkle hashes
        curr_job[5] = blocktemplate["result"]["version"]
        curr_job[6] = blocktemplate["result"]["curtime"]
        self.curr_job = curr_job
        self.block_height = blocktemplate["result"]["height"]
        return
    # set up switch statement using dictionary containing all the stratum methods as detailed in https://en.bitcoin.it/wiki/Stratum_mining_protocol
    methods = {
        "mining.authorize": authorize,
        "mining.capabilities": capabilities,
        "mining.extranonce.subscribe": extranonce_subscribe,
        "mining.get_transactions": get_transactions,
        "mining.submit": submit,
        "mining.subscribe": subscribe,
        "mining.suggest_difficulty": suggest_difficulty,
        "mining.suggest_target": suggest_target,
        "daemon.blocknotify": blocknotify  # not part of stratum - notifications from daemon
    }

    # check for valid json by trying to load it
    try:
        message = json.loads(message)
    except:
        log.debug("Recieved invalid json from {}".format(address))
        raise ValueError('Invalid json was received from') # We can raise an error because of the try except in the listner

    # otherwise send the message to the correct method
    else:
        if authorized and message["method"] != "mining.authorize":
            try:
                response = methods[message["method"]]() # no arguments because subfunctions can access parent function vars
            except:
                response = response_template
                response["error"] = "Invalid method!"
        else:
            response = methods["mining.authorize"]
    return (json.dumps(response).encode("utf-8"))


# called by main to start the server thread
def init_server(temp_config, temp_global_config, temp_mongodb_connection, temp_log):
    # init global vars
    global log
    global mongodb_connection
    global clients
    global transport_num
    global config
    global global_config
    global response_template
    global block_height
    global curr_job_id
    global job_template
    global rpc_connection
    # set values to the global variables
    log = temp_log
    mongodb_connection = temp_mongodb_connection
    clients = {}
    transport_num = 0
    config = temp_config
    global_config = temp_global_config
    # generic stratum protocol response
    response_template = config['stratum']['response_template']
    # this is just a variable to add onto so all handler threads can tell when there is a new block
    block_height = 0
    curr_job_id = 1
    job_template = [
        0,  # job_id - ID of the job. Use this ID while submitting share generated from this job.
        0,  # prevhash - Initial part of coinbase transaction.
        0,  # coinb1 - Initial part of coinbase transaction.
        0,  # coinb2 - Final part of coinbase transaction.
        [],
        # merkle_branch - List of hashes, will be used for calculation of merkle root. This is not a list of all transactions, it only contains prepared hashes of steps of merkle tree algorithm.
        0,  # version - Bitcoin block version.
        0,  # nbits - Encoded current network difficulty
        0,  # ntime - Current ntime/
        True  # clean_jobs - When true, server indicates that submitting shares from previous jobs don't have a sense and such shares will be rejected. When this flag is set, miner should also drop all previous jobs, so job_ids can be eventually rotated.
    ]
    # connects to bitcoin daemon with settings from config
    rpc_connection = AuthServiceProxy("http://%s:%s@%s:%s" % (
        config['daemon']["rpc_username"], config['daemon']["rpc_password"],
        config['daemon']["daemon_ip"],
        config['daemon']["daemon_port"]))
    log.debug(config["coin"] + " init complete")
    return socketserver.TCPServer((global_config['ip'], config['port']), TCPServer).serve_forever()
