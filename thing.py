import sys
import asyncio
from dataclasses import dataclass, field
from asyncio import Task
from typing import Dict, Optional, Set

import toml
from discord import (
    Client, Intents, Guild, Member, Message,
    TextChannel, RawReactionActionEvent)


cfg = toml.load('cfg.toml')
client = Client(intents=Intents(members=True, reactions=True, guilds=True))


@dataclass
class GuildCtx:
    # at the disco
    panic: bool           = False
    reset: Optional[Task] = None
    members: Set[Member]  = field(default_factory=lambda: set())


@dataclass
class Incident:
    purger:  Task
    members: Set[Member] = field(default_factory=lambda: set())


joins: Dict[Guild, GuildCtx] = {}
incidents: Dict[int, Incident] = {}


async def purge_incident(msgid: int):
    del incidents[msgid]


async def schedule_incident_purge(msgid: int):
    # wait 3 days
    await asyncio.sleep(86400 * 3)
    await purge_incident(msgid)


async def raid_summary(g: Guild, members: Set[Member]):
    channel: TextChannel = g.system_channel
    msg = 'the following users joined during a potential raid:\n'
    msg += 'react to this message with ✅ to ban them'

    res: Message = await channel.send(msg)
    task = asyncio.create_task(schedule_incident_purge(res.id))
    incidents[res.id] = Incident(task, members)


async def reset_after(g: Guild, secs: float):
    await asyncio.sleep(secs)
    print('cooldown expired. resetting')
    ctx: GuildCtx = joins[g]

    if ctx.panic: await raid_summary(g, ctx.members)
    joins[g] = GuildCtx()


def reschedule_reset(g: Guild, ctx: GuildCtx):
    if ctx.reset:
        try: ctx.reset.cancel()
        except Exception: pass
    ctx.reset = asyncio.create_task(reset_after(g, cfg['cooldown']))


@client.event
async def on_ready():
    print('lets bust sum scammers')


async def purge(m: Member):
    g: Guild = m.guild

    def check_purge(msg: Message): return msg.author.id == m.id
    if g.system_channel:
        await g.system_channel.purge(check=check_purge, limit=10)


async def notify(m: Member):
    try: await m.send(cfg['message'])
    except Exception: pass


async def boot(m: Member):
    await notify(m)
    await asyncio.wait([m.kick(reason='begone heathen machine'), purge(m)])


@client.event
async def on_member_join(m: Member):
    ctx: GuildCtx = joins.setdefault(m.guild, GuildCtx())
    ctx.members.add(m)
    reschedule_reset(m.guild, ctx)
    if ctx.panic: await boot(m)
    elif(len(ctx.members) >= cfg['threshhold']):
        ctx.panic = True
        for m in ctx.members: await boot(m)


@client.event
async def on_raw_reaction_add(p: RawReactionActionEvent):
    if p.member.guild_permissions.ban_members and p.emoji.name == '✅':
        try:
            incident = incidents[p.message_id]
            incident.purger.cancel()
            for m in incident.members:
                try: await m.ban(reason='begone heathen machine')
                except Exception as e: print(f'banning failed: {e}')
            await purge_incident(p.message_id)
            await p.member.guild.system_channel.send('fuck em')
        except Exception: pass

client.run(sys.argv[1])
