# -*- coding: utf-8 -*-
"""Broadcaster: даты, доступ, пожелания, откат события, имена команд."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

from services.broadcaster_catalog import all_tribunes, banner_png, tribune_by_key
from services.broadcaster_config import load_cfg
from services.broadcaster_logic import (
    LOBBY_NAME,
    can_edit_schedule,
    can_touch,
    channel_name,
    due_wish_slots,
    match_named_channel,
    member_is_broadcaster,
    parse_start,
    permission_plan,
    pick_wish,
    tribune_is_due,
    validate_start,
    zone,
)
from services import broadcaster_store as store
from services import broadcaster_actions as actions


MSK = ZoneInfo('Europe/Moscow')


class LogicTests(unittest.TestCase):
    def test_catalog_unique_and_banner_is_png(self):
        keys = [x['key'] for x in all_tribunes()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 8)
        item = tribune_by_key('love')
        blob = banner_png(item)
        self.assertTrue(blob.startswith(b'\x89PNG'))
        self.assertLess(len(blob), 400_000)
        self.assertIsNone(tribune_by_key('nope'))

    def test_parse_rejects_garbage_and_past(self):
        now = datetime(2026, 10, 11, 12, 0, tzinfo=MSK)
        bad, err = parse_start('32.13.2026', '21:00', MSK)
        self.assertIsNone(bad)
        self.assertIn('Дата', err)
        bad, err = parse_start('11.10.2026', '25:99', MSK)
        self.assertIsNone(bad)
        self.assertIn('Время', err)
        local, err = parse_start('11.10.2026', '21:00', MSK)
        self.assertEqual(err, '')
        self.assertEqual(local.astimezone(timezone.utc).hour, 18)
        morning, _err = parse_start('11.10.2026', '10:00', MSK)
        self.assertIn('уже прошло', validate_start(morning, now))
        future = now + timedelta(days=1)
        self.assertEqual(validate_start(future, now), '')
        self.assertIn('далеко', validate_start(now + timedelta(days=91), now))

    def test_only_owner_and_only_broadcaster(self):
        row = {'owner_id': 5, 'status': 'scheduled', 'starts_at': '2026-10-12T18:00:00+00:00'}
        self.assertTrue(can_touch(5, row)[0])
        ok, why = can_touch(9, row)
        self.assertFalse(ok)
        self.assertIn('своими', why)
        self.assertFalse(can_touch(5, {'owner_id': 5, 'status': 'deleted'})[0])
        self.assertTrue(can_edit_schedule(row)[0])
        opened = dict(row, status='opened')
        self.assertFalse(can_edit_schedule(opened)[0])
        self.assertTrue(member_is_broadcaster([1, 155], 155))
        self.assertFalse(member_is_broadcaster([1], 155))
        self.assertFalse(member_is_broadcaster([155], 0))

    def test_permissions_closed_then_open(self):
        closed = permission_plan(opened=False, has_gender=True)
        self.assertFalse(closed['everyone']['view_channel'])
        self.assertFalse(closed['everyone']['connect'])
        self.assertNotIn('gender', closed)
        opened = permission_plan(opened=True, has_gender=True)
        self.assertTrue(opened['everyone']['view_channel'])
        self.assertFalse(opened['everyone']['connect'])
        self.assertTrue(opened['gender']['connect'])
        self.assertTrue(opened['gender']['speak'])
        fallback = permission_plan(opened=True, has_gender=False)
        self.assertTrue(fallback['everyone']['connect'])
        self.assertNotIn('gender', fallback)

    def test_wishes_do_not_repeat_and_slots_fire_once_a_day(self):
        messages = ['a', 'b', 'c', 'd', 'e']
        rng = __import__('random').Random(1)
        deck, last = [], None
        seen_pairs = []
        for _ in range(30):
            choice, deck, last = pick_wish(messages, deck, last, rng)
            seen_pairs.append(choice)
            self.assertIn(choice, messages)
        for prev, cur in zip(seen_pairs, seen_pairs[1:]):
            self.assertNotEqual(prev, cur)
        self.assertGreater(len(set(seen_pairs)), 1)
        empty, _deck, _last = pick_wish([], [], None)
        self.assertIsNone(empty)

        morning = datetime(2026, 10, 11, 10, 1, tzinfo=MSK)
        self.assertEqual(
            due_wish_slots(morning, ['10:00', '21:00'], []),
            ['2026-10-11 10:00'],
        )
        early = morning.replace(hour=9, minute=59)
        self.assertEqual(due_wish_slots(early, ['10:00', '21:00'], []), [])
        late = morning.replace(hour=10, minute=30)
        self.assertEqual(due_wish_slots(late, ['10:00', '21:00'], [], grace_minutes=20), [])
        evening = morning.replace(hour=21, minute=5)
        sent = {'2026-10-11 10:00'}
        self.assertEqual(
            due_wish_slots(evening, ['10:00', '21:00'], sent),
            ['2026-10-11 21:00'],
        )
        self.assertEqual(due_wish_slots(evening, ['99:00', 'nope'], []), [])

    def test_due_tribune_and_names(self):
        now = datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)
        self.assertTrue(tribune_is_due(
            '2026-10-11T17:00:00+00:00', now, 'scheduled'))
        self.assertFalse(tribune_is_due(
            '2026-10-11T19:00:00+00:00', now, 'scheduled'))
        self.assertFalse(tribune_is_due(
            '2026-10-11T17:00:00+00:00', now, 'opened'))
        self.assertEqual(channel_name('  Любовная\nтрибуна #1  '), 'Любовная трибуна 1')
        self.assertEqual(channel_name(''), 'трибуна')
        self.assertEqual(len(channel_name('я' * 200)), 100)
        self.assertEqual(LOBBY_NAME, 'войти в лав руму')
        self.assertEqual(
            match_named_channel(['общий', 'пожелания-дня'], ['пожелан']),
            'пожелания-дня',
        )

    def test_config_defaults(self):
        cfg = load_cfg(os.path.join('config', 'broadcaster.json'))
        self.assertEqual(cfg['love']['lobby_name'], LOBBY_NAME)
        self.assertEqual(cfg['wishes']['times'], ['10:00', '21:00'])
        self.assertEqual(int(cfg['wishes']['delete_after_minutes']), 30)
        self.assertGreaterEqual(len(cfg['wishes']['messages']), 10)
        self.assertEqual(cfg['timezone'], 'Europe/Moscow')
        self.assertEqual(zone('Not/AZone').key, 'Europe/Moscow')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store.set_db_path(os.path.join(self.tmp.name, 'b.db'))

    def tearDown(self):
        store.set_db_path(None)
        self.tmp.cleanup()

    def test_claim_open_and_wish_slot_once(self):
        row = store.insert_tribune(
            guild_id=1, owner_id=5, catalog_key='love', title='Любовная трибуна',
            starts_at='2026-10-11T18:00:00+00:00', channel_id=10, event_id=20,
        )
        self.assertTrue(store.claim_open(row['id']))
        self.assertFalse(store.claim_open(row['id']))
        store.release_open(row['id'])
        self.assertTrue(store.claim_open(row['id']))
        self.assertTrue(store.claim_wish_slot('2026-10-11 10:00'))
        self.assertFalse(store.claim_wish_slot('2026-10-11 10:00'))
        store.release_wish_slot('2026-10-11 10:00')
        self.assertTrue(store.claim_wish_slot('2026-10-11 10:00'))
        store.schedule_wish_delete(99, 7, '2020-01-01T00:00:00+00:00')
        self.assertEqual(len(store.due_wish_deletes('2026-01-01T00:00:00+00:00')), 1)
        store.finish_wish_delete(99)
        self.assertEqual(store.due_wish_deletes('2026-01-01T00:00:00+00:00'), [])

    def test_due_compares_instants_not_clock_strings(self):
        row = store.insert_tribune(
            guild_id=1, owner_id=5, catalog_key='night', title='Ночная трибуна',
            starts_at='2026-10-11T21:00:00+03:00', channel_id=1, event_id=2,
        )
        # 21:00 в Москве уже наступило в 18:05 UTC, хотя строка «21» больше «18»
        due = store.due_tribunes('2026-10-11T18:05:00+00:00')
        self.assertEqual([r['id'] for r in due], [row['id']])
        self.assertEqual(store.due_tribunes('2026-10-11T17:00:00+00:00'), [])


def _guild():
    guild = MagicMock()
    guild.id = 1
    guild.default_role = MagicMock(id=1)
    guild.me = MagicMock(id=50)
    guild.categories = []
    guild.voice_channels = []
    guild.text_channels = []
    guild.system_channel = None
    host = MagicMock(id=155)
    male = MagicMock(id=804)
    guild.get_role = lambda rid: {155: host, 804: male}.get(int(rid))
    category = MagicMock()
    category.id = 9
    category.name = 'Трибуны'
    category.voice_channels = []
    guild.create_category = AsyncMock(return_value=category)
    return guild


class ActionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        store.set_db_path(os.path.join(self.tmp.name, 'b.db'))
        self.cfg = {
            'broadcaster_role_id': 155,
            'gender_role_ids': [804],
            'tribune_category_id': 0,
            'announce_channel_id': 0,
            'event_duration_minutes': 120,
            'love': {'lobby_name': LOBBY_NAME, 'room_name': 'лав рума', 'user_limit': 2},
        }

    def tearDown(self):
        store.set_db_path(None)
        self.tmp.cleanup()

    async def test_create_rolls_back_channel_when_event_fails(self):
        guild = _guild()
        voice = MagicMock()
        voice.id = 33
        voice.mention = '<#33>'
        voice.delete = AsyncMock()
        guild.create_stage_channel = AsyncMock(side_effect=RuntimeError('no stage'))
        guild.create_voice_channel = AsyncMock(return_value=voice)
        guild.create_scheduled_event = AsyncMock(side_effect=RuntimeError('discord said no'))
        start = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
        ok, text, row = await actions.create_tribune(
            guild, self.cfg, owner_id=5, catalog_key='love', start=start,
        )
        self.assertFalse(ok)
        self.assertIsNone(row)
        self.assertIn('не создалось', text)
        voice.delete.assert_awaited()
        self.assertEqual(store.list_live(1), [])

    async def test_create_stores_row(self):
        guild = _guild()
        voice = MagicMock()
        voice.id = 33
        voice.mention = '<#33>'
        guild.create_stage_channel = AsyncMock(return_value=voice)
        event = MagicMock()
        event.id = 77
        event.url = 'https://discord.com/events/1/77'
        guild.create_scheduled_event = AsyncMock(return_value=event)
        start = datetime(2026, 10, 12, 21, 0, tzinfo=MSK)
        ok, text, row = await actions.create_tribune(
            guild, self.cfg, owner_id=5, catalog_key='music', start=start,
        )
        self.assertTrue(ok, text)
        self.assertEqual(row['owner_id'], 5)
        self.assertEqual(row['catalog_key'], 'music')
        self.assertEqual(int(row['event_id']), 77)
        kwargs = guild.create_scheduled_event.await_args.kwargs
        self.assertTrue(kwargs['image'].startswith(b'\x89PNG'))
        self.assertEqual(kwargs['channel'], voice)
        self.assertIn('Музыкальная', text)

    async def test_delete_foreign_is_callers_job_and_missing_event_is_ok(self):
        guild = _guild()
        row = store.insert_tribune(
            guild_id=1, owner_id=5, catalog_key='talk', title='Общая трибуна',
            starts_at='2026-10-12T18:00:00+00:00', channel_id=33, event_id=77,
        )
        guild.get_scheduled_event = MagicMock(return_value=None)

        async def _fetch_event(_eid):
            raise __import__('discord').NotFound(MagicMock(), 'missing')

        guild.fetch_scheduled_event = AsyncMock(side_effect=_fetch_event)
        channel = MagicMock()
        channel.delete = AsyncMock()
        guild.get_channel = MagicMock(return_value=channel)
        ok, text = await actions.delete_tribune(guild, row)
        self.assertTrue(ok, text)
        self.assertEqual(store.get_tribune(row['id'])['status'], 'deleted')
        channel.delete.assert_awaited()

    async def test_love_move_failure_removes_room(self):
        guild = _guild()
        lobby = MagicMock()
        lobby.category = MagicMock()
        room = MagicMock()
        room.id = 404
        room.delete = AsyncMock()
        guild.create_voice_channel = AsyncMock(return_value=room)
        member = MagicMock()
        member.id = 8
        member.move_to = AsyncMock(side_effect=RuntimeError('no move'))
        got = await actions.spawn_love_room(guild, self.cfg, member, lobby)
        self.assertIsNone(got)
        self.assertFalse(store.is_love(404))
        room.delete.assert_awaited()

    async def test_open_retries_later_if_channel_missing(self):
        guild = _guild()
        row = store.insert_tribune(
            guild_id=1, owner_id=5, catalog_key='talk', title='Общая трибуна',
            starts_at='2020-01-01T00:00:00+00:00', channel_id=1, event_id=0,
        )
        guild.get_channel = MagicMock(return_value=None)
        guild.fetch_channel = AsyncMock(side_effect=RuntimeError('gone'))
        self.assertTrue(store.claim_open(row['id']))
        ok, why = await actions.open_tribune(guild, self.cfg, store.get_tribune(row['id']))
        self.assertFalse(ok)
        self.assertIn('недоступен', why)
        store.release_open(row['id'])
        self.assertEqual(store.get_tribune(row['id'])['status'], 'scheduled')


class CommandTreeTests(unittest.IsolatedAsyncioTestCase):
    async def test_slash_names_match_spec(self):
        import discord
        from discord.ext import commands
        from services.broadcaster_cog import BroadcasterCog, command_paths

        intents = discord.Intents.none()
        bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
        await bot.add_cog(BroadcasterCog(bot))
        names = set(command_paths(bot))
        self.assertIn('create tribune', names)
        self.assertIn('delete tribune', names)
        self.assertIn('edit tribune', names)


if __name__ == '__main__':
    unittest.main()
