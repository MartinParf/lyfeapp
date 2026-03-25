from huey import RedisHuey

# Placeholder for future async tasks.
# We will likely switch transport/backend strategy later,
# but this file gives us one stable import location.
huey = RedisHuey("lyfeapp")