import json
import logging
import asyncio
class StratumServerProtocol(asyncio.Protocol):
    def __init__(self):
        logging.basicConfig(format="%(levelname)s:%(module)s:%(message)s", level=logging.INFO)
        self.log = logging.getLogger(__name__)
    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.log.info('Connection from {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        self.log.debug('Data received: {!r}'.format(message))
        
        try:
            json.loads(message)
        except:
            self.log.info("Invalid data recieved - " + str(message))
            self.transport.write("bruh")
            self.transport.close()
        
        
        self.log.debug('Send: {!r}'.format(message))
        self.transport.write(data)

        self.log.debug('Close the client socket')
        self.transport.close()

async def main(config, global_config):
    loop = asyncio.get_running_loop()
        
    # pro tip - the config passed to it is the coin specific one and the self.config is the global config
    server = await loop.create_server(
        lambda: StratumServerProtocol(),
        global_config['ip'], config['port'])

    async with server:
        await server.serve_forever()