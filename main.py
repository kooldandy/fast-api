from app.app import app
from mangum import Mangum

handler = Mangum(app)

if __name__ == "__main__":
    import uvicorn

    #Local
    # uvicorn.run(app, host="localhost", port=8000)
    #PROD
    uvicorn.run(app, host="0.0.0.0", port=8000)
