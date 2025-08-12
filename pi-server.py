import asyncio
import websockets
import json
import click

HOST = "0.0.0.0"
Port = 8765

async def handler(ws, path):
    click.secho(f"Laptop Connected", fg = "blue")

    #for testing we are sending a create-button command
    create_cmd = {
        "action" : "create",
        "widget" : "button",
        "id" : "btn1",
        "props" : {
            "text": "Press me (from pi)",
            "x" : 50,
            "y" : 50
        }
    }
    await ws.send(json.dumps(create_cmd))
    click.secho("sent create command to client", fg = "green")

    #waiting for events from client
    try:
        async for msg in ws:
            data = json.loads(msg)
            click.secho(f"Received from client: {data}", fg = "blue")
            #for demo, reply back
            if data.get("action") == "event":
                await ws.send(json.dumps({"action":"ack","detail":"received event"}))
    
    except websockets.ConnectionClosed:
        click.secho("client disconnected")

async def main():
    click.secho(f"Starting Pi server on ws://{HOST}:{Port}", fg = "green")
    async with websockets.serve(handler, HOST, Port):
        await asyncio.Future() #to run forever

if __name__ == "__main__":
    asyncio.run(main())