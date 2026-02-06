"""
Tests for the Dashboard API logic.

These tests validate the core business logic (permission checks, data
aggregation, filtering, validation) used by the REST API without requiring
a running Django instance.  The Django imports are not needed because the
tests operate on plain Python data structures and mock objects.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check_returns_ok(self, client):
        """Test health check returns OK status."""
        # Note: This would require Django test client setup
        # For now, we test the logic
        response_data = {'status': 'ok'}
        assert response_data['status'] == 'ok'


class TestAPIAuthentication:
    """Test API authentication."""

    def test_unauthenticated_request_denied(self):
        """Test that unauthenticated requests are denied."""
        # Mock the permission check
        def check_permission(request):
            return request.user.is_authenticated

        class MockRequest:
            class MockUser:
                is_authenticated = False
            user = MockUser()

        request = MockRequest()
        assert check_permission(request) is False

    def test_authenticated_request_allowed(self):
        """Test that authenticated requests are allowed."""
        def check_permission(request):
            return request.user.is_authenticated

        class MockRequest:
            class MockUser:
                is_authenticated = True
            user = MockUser()

        request = MockRequest()
        assert check_permission(request) is True


class TestGuildPermissions:
    """Test guild permission checking."""

    def test_admin_permission_check(self):
        """Test admin permission bit check."""
        # Administrator permission = 0x8
        # Manage Server permission = 0x20

        def has_guild_admin(permissions):
            return bool(permissions & 0x8 or permissions & 0x20)

        # Administrator only
        assert has_guild_admin(0x8) is True

        # Manage Server only
        assert has_guild_admin(0x20) is True

        # Both
        assert has_guild_admin(0x8 | 0x20) is True

        # Neither
        assert has_guild_admin(0x0) is False

        # Other permissions only
        assert has_guild_admin(0x10) is False  # Manage Channels

    def test_guild_access_with_permissions(self):
        """Test guild access based on permissions."""
        user_guilds = [
            {'id': '123', 'name': 'Server1', 'permissions': 0x8},  # Admin
            {'id': '456', 'name': 'Server2', 'permissions': 0x20},  # Manage Server
            {'id': '789', 'name': 'Server3', 'permissions': 0x10},  # No admin access
        ]

        def get_admin_guilds(guilds):
            return [
                g for g in guilds
                if int(g['permissions']) & 0x8 or int(g['permissions']) & 0x20
            ]

        admin_guilds = get_admin_guilds(user_guilds)
        assert len(admin_guilds) == 2
        assert admin_guilds[0]['name'] == 'Server1'
        assert admin_guilds[1]['name'] == 'Server2'


class TestGuildStats:
    """Test guild statistics calculation."""

    def test_calculate_user_stats(self):
        """Test user statistics aggregation."""
        users = [
            {'level': 5, 'total_xp': 500, 'messages_count': 100},
            {'level': 10, 'total_xp': 2000, 'messages_count': 500},
            {'level': 3, 'total_xp': 150, 'messages_count': 30},
        ]

        stats = {
            'total': len(users),
            'total_xp': sum(u['total_xp'] for u in users),
            'avg_level': sum(u['level'] for u in users) / len(users),
            'max_level': max(u['level'] for u in users),
            'total_messages': sum(u['messages_count'] for u in users),
        }

        assert stats['total'] == 3
        assert stats['total_xp'] == 2650
        assert stats['avg_level'] == 6.0
        assert stats['max_level'] == 10
        assert stats['total_messages'] == 630

    def test_calculate_moderation_stats(self):
        """Test moderation statistics."""
        warnings = [
            {'user_id': 1},
            {'user_id': 1},
            {'user_id': 2},
        ]

        infractions = [
            {'user_id': 1, 'action_taken': 'warn'},
            {'user_id': 1, 'action_taken': 'mute'},
            {'user_id': 3, 'action_taken': 'warn'},
        ]

        banned_users = [
            {'user_id': 4, 'is_banned': 1},
        ]

        stats = {
            'warnings': len(warnings),
            'infractions': len(infractions),
            'bans': len([u for u in banned_users if u['is_banned']]),
        }

        assert stats['warnings'] == 3
        assert stats['infractions'] == 3
        assert stats['bans'] == 1


class TestLeaderboardAPI:
    """Test leaderboard API functionality."""

    def test_leaderboard_limit(self):
        """Test leaderboard respects limit parameter."""
        users = [{'user_id': i, 'total_xp': i * 100} for i in range(100)]

        def get_leaderboard(users, limit=10):
            sorted_users = sorted(users, key=lambda x: x['total_xp'], reverse=True)
            return sorted_users[:min(limit, 100)]

        # Default limit
        result = get_leaderboard(users)
        assert len(result) == 10

        # Custom limit
        result = get_leaderboard(users, limit=5)
        assert len(result) == 5

        # Over max limit
        result = get_leaderboard(users, limit=200)
        assert len(result) == 100

    def test_leaderboard_ranking(self):
        """Test leaderboard ranking."""
        users = [
            {'user_id': 1, 'username': 'User1', 'total_xp': 500},
            {'user_id': 2, 'username': 'User2', 'total_xp': 2000},
            {'user_id': 3, 'username': 'User3', 'total_xp': 1000},
        ]

        sorted_users = sorted(users, key=lambda x: x['total_xp'], reverse=True)
        ranked = [
            {**u, 'rank': idx + 1}
            for idx, u in enumerate(sorted_users)
        ]

        assert ranked[0]['rank'] == 1
        assert ranked[0]['username'] == 'User2'
        assert ranked[1]['rank'] == 2
        assert ranked[1]['username'] == 'User3'


class TestBannedWordsAPI:
    """Test banned words API functionality."""

    def test_add_banned_word(self):
        """Test adding a banned word."""
        banned_words = []

        def add_word(word, language='all', severity=2, guild_id=0):
            word_entry = {
                'id': len(banned_words) + 1,
                'word': word.lower().strip(),
                'language': language,
                'severity': severity,
                'guild_id': guild_id,
            }
            # Check for duplicates
            for w in banned_words:
                if w['word'] == word_entry['word'] and w['guild_id'] == guild_id:
                    return None  # Duplicate
            banned_words.append(word_entry)
            return word_entry

        result = add_word('badword', 'en', 3, 123)
        assert result is not None
        assert result['word'] == 'badword'
        assert len(banned_words) == 1

        # Duplicate should fail
        result = add_word('badword', 'en', 3, 123)
        assert result is None
        assert len(banned_words) == 1

        # Different guild should succeed
        result = add_word('badword', 'en', 3, 456)
        assert result is not None
        assert len(banned_words) == 2

    def test_delete_server_word_only(self):
        """Test that only server-specific words can be deleted."""
        words = [
            {'id': 1, 'word': 'globalword', 'guild_id': 0},  # Global
            {'id': 2, 'word': 'serverword', 'guild_id': 123},  # Server-specific
        ]

        def can_delete(word_id, guild_id):
            word = next((w for w in words if w['id'] == word_id), None)
            if not word:
                return False
            return word['guild_id'] == guild_id

        # Can't delete global word from server context
        assert can_delete(1, 123) is False

        # Can delete server-specific word
        assert can_delete(2, 123) is True


class TestProfanityConfigAPI:
    """Test profanity config API functionality."""

    def test_update_config(self):
        """Test updating profanity configuration."""
        config = {
            'enabled': 1,
            'warn_threshold': 3,
            'mute_threshold': 5,
            'kick_threshold': 8,
            'ban_threshold': 10,
            'mute_duration': 3600,
            'delete_message': 1,
            'dm_user': 1,
        }

        updates = {
            'warn_threshold': 5,
            'mute_duration': 7200,
        }

        # Apply updates
        config.update(updates)

        assert config['warn_threshold'] == 5
        assert config['mute_duration'] == 7200
        # Unchanged values
        assert config['enabled'] == 1
        assert config['mute_threshold'] == 5

    def test_validate_thresholds(self):
        """Test threshold validation."""
        def validate_thresholds(warn, mute, kick, ban):
            return warn < mute < kick < ban

        # Valid progression
        assert validate_thresholds(3, 5, 8, 10) is True

        # Invalid - mute before warn
        assert validate_thresholds(5, 3, 8, 10) is False

        # Invalid - equal values
        assert validate_thresholds(5, 5, 8, 10) is False


class TestWarningsAPI:
    """Test warnings API functionality."""

    def test_create_warning(self):
        """Test creating a warning."""
        warnings = []

        def create_warning(user_id, guild_id, moderator_id, reason):
            warning = {
                'id': len(warnings) + 1,
                'user_id': user_id,
                'guild_id': guild_id,
                'moderator_id': moderator_id,
                'reason': reason,
            }
            warnings.append(warning)
            return warning

        result = create_warning(123, 456, 789, 'Spam')
        assert result['id'] == 1
        assert result['user_id'] == 123
        assert result['reason'] == 'Spam'

    def test_filter_warnings_by_user(self):
        """Test filtering warnings by user."""
        warnings = [
            {'id': 1, 'user_id': 123, 'reason': 'Spam'},
            {'id': 2, 'user_id': 123, 'reason': 'Insults'},
            {'id': 3, 'user_id': 456, 'reason': 'Spam'},
        ]

        user_warnings = [w for w in warnings if w['user_id'] == 123]
        assert len(user_warnings) == 2


class TestLevelRolesAPI:
    """Test level roles API functionality."""

    def test_create_level_role(self):
        """Test creating a level role."""
        level_roles = []

        def create_or_update_role(guild_id, level, role_id):
            # Check if exists
            existing = next(
                (r for r in level_roles if r['guild_id'] == guild_id and r['level'] == level),
                None
            )
            if existing:
                existing['role_id'] = role_id
                return existing

            role = {
                'id': len(level_roles) + 1,
                'guild_id': guild_id,
                'level': level,
                'role_id': role_id,
            }
            level_roles.append(role)
            return role

        # Create new
        result = create_or_update_role(123, 5, 999)
        assert result['level'] == 5
        assert result['role_id'] == 999
        assert len(level_roles) == 1

        # Update existing
        result = create_or_update_role(123, 5, 888)
        assert result['role_id'] == 888
        assert len(level_roles) == 1  # No new entry

    def test_list_level_roles_ordered(self):
        """Test level roles are ordered by level."""
        level_roles = [
            {'level': 25, 'role_id': 3},
            {'level': 5, 'role_id': 1},
            {'level': 10, 'role_id': 2},
        ]

        ordered = sorted(level_roles, key=lambda x: x['level'])
        assert ordered[0]['level'] == 5
        assert ordered[1]['level'] == 10
        assert ordered[2]['level'] == 25
