# coding=utf-8
import logging
import os
import subprocess
from asyncio import sleep
from datetime import datetime
from random import shuffle
from shutil import copy2
from discord import Game, utils, Embed, Colour, DiscordException, Activity, ActivityType

from core.stats import MESSAGE
from core.utils import is_valid_command, log_to_file, StandardEmoji, resolve_time
from core.confparser import get_settings_parser, BACKUP_DIR, DATA_DIR

#######################
# NOT TRANSLATED
#######################

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# settings.ini
parser = get_settings_parser()


game_list = [
    "Hi there!",
    "HI MOM!",
    "@Nano",
    "fun games",
    "with discord.py",
    "with DefaltSimon",
    "with Discord",
    "with python",
    "nano.invite",
    "party hard (▀̿Ĺ̯▀̿ ̿)",
    "nanobot.pw",
    "nanobot.pw/commands.html",
    ""
]

commands = {
    "nano.dev": {"desc": "Developer commands, restricted."},
    "nano.playing": {"desc": "Restricted to owner, changes 'playing' status.", "use": "[command] [status]"},
    "nano.restart": {"desc": "Restricted to owner, restarts down the bot.", "use": "[command]"},
    "nano.reload": {"desc": "Restricted to owner, reloads all settings from config file.", "alias": "_reload"},
    "nano.kill": {"desc": "Restricted to owner, shuts down the bot.", "use": "[command]"},
}

valid_commands = commands.keys()


class StatusRoller:
    def __init__(self, client, time=21600):  # 6 Hours
        log.info("Status changer enabled")

        self.time = time
        self.client = client

    async def change_status(self, name):
        log.debug("Changing status to {}".format(name))
        log_to_file("Changing status to {}".format(name))

        shards = list(self.client.shards.keys())
        for shard_id in shards:
            customized = name + " | shard {}".format(shard_id + 1)
            await self.client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="you"))

    async def run(self):
        await self.client.wait_until_ready()

        # Shuffle the game list in place
        shuffle(game_list)

        for game in game_list:
            await self.change_status(game)
            await sleep(self.time)

            if self.client.is_closed:
                break

        # Shuffle when the whole list is used
        shuffle(game_list)

        log_to_file("Exited status changer")


class BackupManager:
    def __init__(self, time=86400, keep_backup_every=3):  # 86400 seconds = one day (backup is executed once a day)
        log.info("Backup enabled")

        self.s_path = os.path.join(DATA_DIR, "data.rdb")
        self.s_path_d = os.path.join(BACKUP_DIR, "data.rdb.bak")

        if not os.path.isdir(BACKUP_DIR):
            os.mkdir(BACKUP_DIR)

        self.time = int(time)
        self.keep_every = int(keep_backup_every)
        self.temp_keep = int(self.keep_every)

        self.enabled = True

    def disable(self):
        self.enabled = False

    def backup(self, make_dated_backup=False):
        if not self.enabled:
            return

        if not os.path.isdir(BACKUP_DIR):
            os.mkdir(BACKUP_DIR)

        # Make a dated backup if needed
        # Dated backups are located in a directory named "full"
        if make_dated_backup:
            path_full = os.path.join(BACKUP_DIR, "full")

            if not os.path.isdir(path_full):
                os.mkdir(path_full)

            bkp_name = "data{}.rdb".format(str(datetime.now().strftime("%d-%B-%Y_%H-%M-%S")))
            bkp_path = os.path.join(BACKUP_DIR, "full", bkp_name)
            copy2(self.s_path, bkp_path)
            log.info("Created a dated backup.")

        # Always copy one to .bak
        try:
            copy2(self.s_path, self.s_path_d)
        except FileNotFoundError:
            pass

    def manual_backup(self, make_dated_backup=True):
        self.backup(make_dated_backup)
        log.info("Manual backup complete")

    async def start(self):
        while self.enabled:
            # Run the backup every day or as specified
            await sleep(self.time)

            # Full backup counter
            self.temp_keep -= 1

            if self.temp_keep <= 0:
                dated_backup = True
                self.temp_keep = int(self.keep_every)
            else:
                dated_backup = False

            log_to_file("Creating a backup...")
            self.backup(dated_backup)


class DevFeatures:
    def __init__(self, **kwargs):
        self.nano = kwargs.get("nano")
        self.handler = kwargs.get("handler")
        self.client = kwargs.get("client")
        self.stats = kwargs.get("stats")
        self.loop = kwargs.get("loop")
        self.trans = kwargs.get("trans")

        self.backup = BackupManager()
        self.roller = StatusRoller(self.client)

        self.shutdown_mode = None

        self.default_channel = None

    async def on_plugins_loaded(self):
        self.default_channel = self.nano.get_plugin("server").instance.default_channel

    async def on_message(self, message, **kwargs):
        client = self.client

        prefix = kwargs.get("prefix")
        lang = kwargs.get("lang")

        # Check if this is a valid command
        if not is_valid_command(message.content, commands, prefix):
            return
        else:
            self.stats.add(MESSAGE)

        def startswith(*matches):
            for match in matches:
                if message.content.startswith(match):
                    return True

            return False

        # Global owner filter

        if not self.handler.is_bot_owner(message.author.id):
            await message.channel.send(self.trans.get("PERM_OWNER", lang))
            return

        # nano.dev.server_info [id]
        elif startswith("nano.dev.server_info"):
            s_id = message.content[len("nano.dev.server_info "):]

            srv = utils.find(lambda b: b.id == s_id, client.guilds)

            if not srv:
                await message.channel.send("No such guild. " + StandardEmoji.CROSS)
                return

            nano_data = self.handler.get_server_data(srv)
            to_send = "{}\n```css\nMember count: {}\nChannels: {}\nOwner: {}```\n" \
                      "*Settings*: ```{}```".format(srv.name, srv.member_count, ",".join([ch.name for ch in srv.channels]), srv.owner.name, nano_data)

            await message.channel.send(to_send)

        # nano.dev.test_exception
        elif startswith("nano.dev.test_exception"):
            int("abcdef")

        # nano.dev.embed_test
        elif startswith("nano.dev.embed_test"):
            emb = Embed(title="Stats", colour=Colour.darker_grey())
            emb.add_field(name="Messages Sent", value="sample messages")

            await message.channel.send("Stats", embed=emb)

        # nano.dev.backup
        elif startswith("nano.dev.backup"):
            self.backup.manual_backup()
            await message.channel.send("Backup completed " + StandardEmoji.PERFECT)

        # nano.dev.leave_server
        elif startswith("nano.dev.leave_server"):
            try:
                sid = int(message.content[len("nano.dev.leave_server "):])
            except ValueError:
                await message.channel.send("Not a number.")
                return

            srv = await self.client.get_guild(sid)
            await srv.leave()
            await message.channel.send("Left {}".format(srv.id))

        # nano.dev.tf.reload
        elif startswith("nano.dev.tf.clean"):
            self.nano.get_plugin("tf2").instance.tf.request()

            await message.channel.send("Re-downloaded data...")

        # nano.dev.plugin.reload
        elif startswith("nano.dev.plugin.reload"):
            name = message.content[len("nano.dev.plugin.reload "):]

            v_old = self.nano.get_plugin(name).plugin.NanoPlugin.version
            s = await self.nano.reload_plugin(name)
            v_new = self.nano.get_plugin(name).plugin.NanoPlugin.version

            if s:
                await message.channel.send("Successfully reloaded **{}**\nFrom version *{}* to *{}*.".format(name, v_old, v_new))
            else:
                await message.channel.send("Something went wrong, check the logs.")

        # nano.dev.servers.clean
        elif startswith("nano.dev.servers.tidy"):
            self.handler.delete_server_by_list([s.id for s in self.client.guilds])

        # nano.restart
        elif startswith("nano.restart"):
            await message.channel.send("**DED, but gonna come back**")

            await client.logout()

            self.shutdown_mode = "restart"
            return "shutdown"

        # nano.kill
        elif startswith("nano.kill"):
            await message.channel.send("**DED**")

            await client.logout()

            self.shutdown_mode = "exit"
            return "shutdown"

        # nano.playing
        elif startswith("nano.playing"):
            status = message.content[len("nano.playing "):]

            await client.change_presence(activity=Game(name=str(status)))
            await message.channel.send("Status changed " + StandardEmoji.THUMBS_UP)

        # nano.dev.translations.reload
        elif startswith("nano.dev.translations.reload"):
            self.trans.reload_translations()

            await message.channel.send(StandardEmoji.PERFECT)

        # nano.dev.test_default_channel
        elif startswith("nano.dev.test_default_channel"):
            df = await self.default_channel(message.guild)

            if not df:
                await message.channel.send("No default channel? w a t")
                return

            await message.channel.send("Default channel is {}, sending test message".format(df.mention))
            await df.send("This is a test message. Apparently everything is ok.")

        # nano.dev.announce
        elif startswith("nano.dev.announce"):
            await message.channel.send("Sending... ")
            ann = message.content[len("nano.dev.announce "):]

            s = []
            for g in self.client.guilds:
                try:
                    d_chan = await self.default_channel(g)
                    await d_chan.send(ann)
                    log_to_file("Sent announcement for {}".format(g.name))
                    s.append(g.name)
                except DiscordException:
                    log_to_file("Couldn't send announcement for {}".format(g.name))

            await message.channel.send("Sent to {} servers".format(len(s)))

        # nano.dev.userdetective

        elif startswith("nano.dev.userdetective"):
            param = str(message.content[len(prefix + "nano.dev.userdetective"):])

            # Number
            if param.isdigit():
                user = self.client.get_user(int(param))
                if not user:
                    await message.channel.send("No user with such ID.")
                    return
            elif len(message.mentions) > 0:
                user = message.mentions[0]
            else:
                members = [user for user in self.client.get_all_members()
                           if user.name == param]

                if not members:
                    await message.channel.send("No users with that name.")
                    return

                user = members[0]

            srv_in_common = 0
            server_table_temp = []
            # Loop though servers and find ones the user is in
            for srv in self.client.guilds:
                mem = srv.get_member(user.id)
                if mem:
                    srv_in_common += 1
                    server_table_temp.append("{}: {}".format(srv.name, mem.display_name))


            join_time_ago = int((datetime.now() - user.created_at).total_seconds())
            join_time_ago = resolve_time(join_time_ago, "en")

            embed = Embed(title="{}#{}{}".format(user.name, user.discriminator, ":robot:" if user.bot else ""), description="ID: {}".format(user.id))
            embed.add_field(name="Joined Discord", value="**{}** ago\nISO time: {}".format(join_time_ago, user.created_at))
            embed.add_field(name="Avatar url", value=user.avatar_url_as(format="png"))
            embed.add_field(name="Servers in common", value="**{}** on this shard:\n```http\n{}```".format(srv_in_common, "\n".join(server_table_temp)))

            await message.channel.send(embed=embed)


    async def on_ready(self):
        self.loop.create_task(self.backup.start())
        self.loop.create_task(self.roller.run())

    async def on_shutdown(self):
        # Make redis save data with BGSAVE
        self.handler.bg_save()

        if self.shutdown_mode == "restart":
            log.critical("Restarting Nano!")
            # Launches a new instance of Nano...
            if os.name == "nt":
                subprocess.Popen(os.path.abspath("startbot.bat"))
            else:
                subprocess.Popen(os.path.abspath("startbot.sh"), shell=True)


class NanoPlugin:
    name = "Developer Commands"
    version = "27"

    handler = DevFeatures
    events = {
        "on_message": 10,
        "on_ready": 5,
        "on_shutdown": 15,
        "on_plugins_loaded": 5,
        # type : importance
    }
