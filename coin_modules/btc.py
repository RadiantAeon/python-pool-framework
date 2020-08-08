import json
import logging
import socket
import threading
import binascii
import hashlib
import multiprocessing
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from twisted.internet.protocol import Factory
from twisted.protocols.basic import LineReceiver
from twisted.internet import reactor


# "Client simply opens TCP socket and writes requests to the server in the form of JSON messages finished by the newline character \n" - slushpool
# Therefore, this is a newline seperated protocol, so we should use line reciever
class TCPServer(LineReceiver):
    # quote wiki "The factory must be passed to {protocol name}.__init__ when creating a new instance. The factory is used to share state that exists beyond the lifetime of any given connection."
    # see https://twistedmatrix.com/documents/current/core/howto/servers.html
    # each connection is independent of each other inside the protocol class so the class variables in the protocol class are local to the connection
    # only factory vars are "global"
    def __init__(self, factory):
        self.factory = factory
        self.authorized = False

    def connectionMade(self):
        # we won't ever reach this amount of connections at a time - this is also the plain integer limit
        self.factory.curr_job_id = (self.factory.curr_job_id + 1) % 9223372036854775807
        self.factory.log.debug("New connection from {}".format(self.client_address))
    
    # will contain cleanup in the future - for now just print a message
    def connectionLost(self, reason):
        self.factory.log.debug("Lost connection from {} because of {}".format(self.client_address, reason))
    
    def lineRecieved(self, line):        
        self.transport.write(self.handle_message(line, self.client_address))

    def handle_message(self, data, address):

        def authorize(message):
            params = message["params"]
            response = self.factory.response_template.copy()
            # params format for mining.authorize should be in the format of ["slush.miner1", "password"] according to slush pool docs
            if self.mongodb_connection.find_one({"user": params[0], "password": params[1]}):
                response["result"] = True
                self.authorized = True
                self.factory.log.debug("Authorized user {}".format(params[0]))
            else:
                response["result"] = False
                response["error"] = "Unauthorized"
                # we don't need to set self.authorized to False because its redundant
                self.factory.log.debug("Failed login by use {}".format(params[0]))
            return response

        # need to make it so blocknotify isn't attackable - currently anyone can call it to fuck with us
        def blocknotify(message):
            # adds one to the block_num var which each thread checks for so we can broadcast new jobs
            curr_job = self.factory.job_template
            try:
                blocktemplate = self.factory.rpc_connection.getblocktemplate
                if blocktemplate["error"]:
                    raise Exception("Failed getblocktemplate rpc call! Is the bitcoin daemon running?")
                self.factory.log.info("New block at height {}".format(blocktemplate["result"]["height"]))
            except Exception as error:
               self.factory.log.error(error)
            curr_job[1] = blocktemplate["result"]["previousblockhash"]
            coinbase = binascii.a2b_hex(blocktemplate['coinbasetxn']['data'])
            extradata = b'yeet' # you can change this
            original_length = ord(coinbase[41:42])
            curr_job[2] = coinbase[0:41]  # first part of coinbase transaction
            curr_job[3] = coinbase[42:42 + original_length] + extradata + coinbase[42 + original_length:]  # second part of coinbase transaction
            # i have no idea if this is right or wrong for the merkle branches :shrug:
            transaction_list = [coinbase] + [binascii.a2b_hex(a['data']) for a in blocktemplate["result"]["transactions"]]
            curr_job[4] = [hashlib.sha256(hashlib.sha256(transaction).digest()).digest() for transaction in transaction_list]  # hash every transaction twice to make prepared merkle hashes
            curr_job[5] = blocktemplate["result"]["version"]
            curr_job[6] = blocktemplate["result"]["curtime"]
            self.block_target = blocktemplate["target"]
            self.curr_job = curr_job
            self.block_height = blocktemplate["result"]["height"]
            return

        '''
        Miners submit shares using the method "mining.submit". Client submissions contain:

        Worker Name.
        Job ID.
        ExtraNonce2.
        nTime.
        nOnce.
        '''
        # since the miner just sends us the parts of the job we just need to check if they are valid
        def submit(message):

            params = message["params"]
            response = self.factory.response_template.copy()
            if self.factory.extranonce2_size != len(str(params[2])):
                response # uhh thats sketch
            # To produce coinbase, we just concatenate Coinb1 + Extranonce1 + Extranonce2 + Coinb2 together. That's all!
            # extranonce1 is generated by us when the miner sends mining.subscribe
            coinbase = self.factory.job_template[2] + self.extranonce1 + params[2] + self.factory.job_template[3]
            coinbase_hash_bin = hashlib.sha256(hashlib.sha256(binascii.unhexlify(coinbase)).digest()).digest()

            merkle_root = coinbase_hash_bin
            for h in self.merkle_branch:
                merkle_root = hashlib.sha256(hashlib.sha256(merkle_root + binascii.unhexlify(h)))
            merkle_root = binascii.hexlify(merkle_root)

            # note according to slushpool the bytes of the merkle root have to be reversed in the block header to make it little endian
            # version + prevhash + merkle_root + ntime + nbits + nonce + '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'
            block_header = str(self.factory.job_template[5]) + str(self.factory.job_template[1]) + merkle_root[::-1] + str(params[3]) + str(self.factory.job_template[6]) + str(params[4]) + '000000800000000000000000000000000000000000000000000000000000000000000000000000000000000080020000'
            # yoinked from here https://en.bitcoin.it/wiki/Block_hashing_algorithm
            block_header_bin = block_header.decode('hex')
            block_header_hash = hashlib.sha256(hashlib.sha256(block_header_bin).digest()).digest()
            block_header_hash.encode('hex_codec')
            block_header_hash[::-1].encode('hex_codec')
            # example value of block_header_hash at this point '00000000000000001e8d6829a8a21adc5d38d0a473b144b6765798e61f98bd1d'

            num_zeroes = len(block_header_hash) - len(block_header_hash.lstrip('0')) # compare the length with the leading zeroes and without the leading zeroes to get the number of leading zeroes

            target = mongodb_connection.find_one({"job_id": params[0]}) # get the target share for this worker
            if num_zeroes > target:
                if num_zeroes > self.block_target: # we found a block
                    pass
                #do things here
                # also check if it hits the global block difficulty
                pass
            #write to db
        
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
            self.factory.log.debug("Recieved invalid json from {}".format(address))
            raise ValueError('Invalid json was received from') # We can raise an error because of the try except in the listner

        # otherwise send the message to the correct method
        else:
            if self.authorized and message["method"] != "mining.authorize":
                try:
                    response = methods[message["method"]](message) # try calling the corresponding method handler
                except:
                    response = self.factory.response_template
                    response["error"] = "Invalid method!"
            else:
                response = methods["mining.authorize"]
        return (json.dumps(response).encode("utf-8"))

# contains all the "global" vars for the Twisted tcp server
class StratumProtocol(Factory):

    # tells twisted the protocol we want to use
    protocol = TCPServer

    def __init__(self, config, global_config, mongodb_connection, log):
        # set values to variables that we will be using
        # variables with no comments do exactly what the variable name implies
        self.log = log
        self.mongodb_connection = mongodb_connection
        self.config = config
        self.global_config = global_config
        # generic stratum protocol response
        self.response_template = config['stratum']['response_template']
        # this is just a variable to add onto so all handler threads can tell when there is a new block
        self.block_height = 0
        # important for calculating if a share is valid
        self.block_target = 0
        # variable that gets incremented to make a unique id for each connection
        self.curr_job_id = 1
        self.job_template = [
            0,  # job_id - ID of the job. Use this ID while submitting share generated from this job.
            0,  # prevhash - Used to build header - hash of previous block.
            0,  # coinb1 - Initial part of coinbase transaction.
            0,  # coinb2 - Final part of coinbase transaction.
            [], # merkle_branch - List of hashes, will be used for calculation of merkle root. This is not a list of all transactions, it only contains prepared hashes of steps of merkle tree algorithm.
            0,  # version - Bitcoin block version.
            0,  # nbits - Encoded current network difficulty
            0,  # ntime - "Current" ntime/
            True  # clean_jobs - When true, server indicates that submitting shares from previous jobs don't have a sense and such shares will be rejected. When this flag is set, miner should also drop all previous jobs, so job_ids can be eventually rotated.
        ]
        # connects to bitcoin daemon with settings from config
        self.rpc_connection = AuthServiceProxy("http://%s:%s@%s:%s" % (
            config['daemon']["rpc_username"], config['daemon']["rpc_password"],
            config['daemon']["daemon_ip"],
            config['daemon']["daemon_port"]))
        log.debug(config["coin"] + " init complete")


# called by main to start the server thread
def init_server(config, global_config, mongodb_connection, log):
    reactor.listenTCP(config.port, StratumProtocol(config, global_config, mongodb_connection, log))
    reactor.run()
