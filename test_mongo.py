import certifi
from pymongo import MongoClient

uri = "mongodb+srv://carrolldavidaws_db_user:superMongoDB@fdarag.xy1fbbu.mongodb.net/python"

client = MongoClient(
uri,
tlsCAFile=certifi.where(),
serverSelectionTimeoutMS=5000,
)

print(client.admin.command("ping"))
print(client.list_database_names())