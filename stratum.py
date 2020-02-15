import ssl
import asyncio
import aiozmq
import zmq
from jsonrpcserver import method, async_dispatch as dispatch
import json

class Stratum:
    def __init__(self, main_config, config, log, ssl_context):
        self.main_config = main_config
        self.config = config
        self.log = log
        self.ssl_context = ssl_context
        self.template = {"error": null, "id": 0, "result": True}
        self.main()

    @method
    class mining:
        async def authorize(self, username, password):
            return_json = self.template
            return_json.id = 2
            return json.dumps(json.dumps(return_json))

    async def main(self):
        rep = await aiozmq.create_zmq_stream(zmq.REP, bind="tcp://" + str(self.main_config['ip'] + ":" + str(self.config['port'])))
        while True:
            request = await rep.read()
            response = await dispatch(request[0].decode())
            rep.write((str(response).encode(),))

    if __name__ == "__main__":
        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        asyncio.get_event_loop().run_until_complete(main())
