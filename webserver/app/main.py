from fastapi import FastAPI
import json 
import uuid
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import asyncio
import os


from aio_pika import Message, connect

from typing import MutableMapping

from aio_pika.abc import (
    AbstractChannel,
    AbstractConnection,
    AbstractIncomingMessage,
    AbstractQueue,
)

HOST = os.environ["RABBITMQ_HOST"]
USERNAME = os.environ["RABBITMQ_DEFAULT_USER"]
PASSWORD = os.environ["RABBITMQ_DEFAULT_PASS"]


class LGDRequest(BaseModel):
    amountOfFinance: float
    amountInsuredLoan: float
    credLimit: float 
    firstCreditLimit: float
    duration: int
    instalment: float
    numOfApplicants: int
    totalAmountOfFinance: float 

class LGDResponse(BaseModel):
    lgd_predicted: float


class LGDRequestBatch(BaseModel):
    texts: list[LGDRequest]


class LGDResponseBatch(BaseModel):
    response: list[LGDResponse]


class RPCClient:
    connection: AbstractConnection

    channel: AbstractChannel

    callback_queue: AbstractQueue

    def __init__(self) -> None:
        self.futures: MutableMapping[str, asyncio.Future] = {}

    async def connect(self) -> "RPCClient":
        self.connection = await connect(f"amqp://{USERNAME}:{PASSWORD}@{HOST}/")
        self.channel = await self.connection.channel()
        self.callback_queue = await self.channel.declare_queue(exclusive=True)
        await self.callback_queue.consume(self.on_response, no_ack=True)
        return self

    async def on_response(self, message: AbstractIncomingMessage) -> None:
        if message.correlation_id is None:
            print(f"Bad message {message!r}")
            return

        future: asyncio.Future = self.futures.pop(message.correlation_id)
        future.set_result(message.body)

    async def call(self, n: str):
        correlation_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.futures[correlation_id] = future

        await self.channel.default_exchange.publish(
            Message(
                str(n).encode(),
                content_type="text/plain",
                correlation_id=correlation_id,
                reply_to=self.callback_queue.name,
            ),
            routing_key="rpc_queue",
        )

        return await future


app = FastAPI(title="LGD Prediction", description="LGD Prediction API")
#templates = Jinja2Templates(directory="templates")
#app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def app_startup():
    global lgd_rpc 
    lgd_rpc = await RPCClient().connect()


@app.get("/", tags=["HTML"], response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse("docs")


@app.post("/process", tags=["API"], response_model=LGDResponse)
async def process(request: LGDRequest):
    req_body = request.model_dump_json()
    response = json.loads(await lgd_rpc.call(req_body))
    print(response)
    return LGDResponse(**response)
