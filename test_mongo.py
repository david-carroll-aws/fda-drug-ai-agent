import certifi
from pymongo import MongoClient

uri = os.environ["MONGODB_URI"]

client = MongoClient(
uri,
tlsCAFile=certifi.where(),
serverSelectionTimeoutMS=5000,
)

print(client.admin.command("ping"))
print(client.list_database_names())