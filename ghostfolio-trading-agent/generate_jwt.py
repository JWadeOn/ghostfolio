import jwt
import datetime

payload = {
    "user_id": "justinbuckner",
    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
}

secret = "your_super_secret_key"
token = jwt.encode(payload, secret, algorithm="HS256")

print(token)