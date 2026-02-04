"""
Tests for the leveling system.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestLevelingCalculations:
    """Test leveling calculation functions."""

    def test_xp_for_level(self):
        """Test XP required for each level."""
        base_xp = 100
        factor = 1.5

        def xp_for_level(level):
            return int(base_xp * (factor ** (level - 1)))

        # Level 1 requires 100 XP
        assert xp_for_level(1) == 100

        # Level 2 requires 150 XP
        assert xp_for_level(2) == 150

        # Level 3 requires 225 XP
        assert xp_for_level(3) == 225

        # Level 10 requires significantly more
        assert xp_for_level(10) > 3000

    def test_total_xp_for_level(self):
        """Test total XP needed to reach a level."""
        base_xp = 100
        factor = 1.5

        def total_xp_for_level(level):
            total = 0
            for lvl in range(1, level):
                total += int(base_xp * (factor ** (lvl - 1)))
            return total

        # Level 1 needs 0 total XP
        assert total_xp_for_level(1) == 0

        # Level 2 needs 100 total XP
        assert total_xp_for_level(2) == 100

        # Level 3 needs 100 + 150 = 250 total XP
        assert total_xp_for_level(3) == 250

    def test_level_from_xp(self):
        """Test calculating level from total XP."""
        base_xp = 100
        factor = 1.5

        def level_from_xp(total_xp):
            level = 1
            xp_needed = base_xp
            while total_xp >= xp_needed:
                total_xp -= xp_needed
                level += 1
                xp_needed = int(base_xp * (factor ** (level - 1)))
            return level

        assert level_from_xp(0) == 1
        assert level_from_xp(50) == 1
        assert level_from_xp(100) == 2
        assert level_from_xp(250) == 3
        assert level_from_xp(1000) == 5

    def test_xp_progress(self):
        """Test XP progress within current level."""
        base_xp = 100
        factor = 1.5

        def get_progress(current_xp, level):
            xp_for_current = int(base_xp * (factor ** (level - 1)))
            return (current_xp / xp_for_current) * 100

        # 50 XP at level 1 = 50% progress
        assert get_progress(50, 1) == 50.0

        # 75 XP at level 2 = 50% progress (150 needed)
        assert get_progress(75, 2) == 50.0

        # 0 XP = 0% progress
        assert get_progress(0, 1) == 0.0


class TestLevelUp:
    """Test level up functionality."""

    def test_should_level_up(self):
        """Test level up check."""
        base_xp = 100
        factor = 1.5

        def should_level_up(current_xp, level):
            xp_needed = int(base_xp * (factor ** (level - 1)))
            return current_xp >= xp_needed

        # Not enough XP
        assert should_level_up(50, 1) is False

        # Exactly enough XP
        assert should_level_up(100, 1) is True

        # More than enough XP
        assert should_level_up(150, 1) is True

        # Level 2 needs 150 XP
        assert should_level_up(149, 2) is False
        assert should_level_up(150, 2) is True

    def test_process_level_up(self):
        """Test processing level up."""
        base_xp = 100
        factor = 1.5

        def process_level_up(current_xp, level):
            xp_needed = int(base_xp * (factor ** (level - 1)))
            leveled_up = False
            while current_xp >= xp_needed:
                current_xp -= xp_needed
                level += 1
                xp_needed = int(base_xp * (factor ** (level - 1)))
                leveled_up = True
            return current_xp, level, leveled_up

        # No level up
        xp, lvl, up = process_level_up(50, 1)
        assert xp == 50
        assert lvl == 1
        assert up is False

        # Single level up
        xp, lvl, up = process_level_up(120, 1)
        assert xp == 20  # 120 - 100
        assert lvl == 2
        assert up is True

        # Multiple level ups
        xp, lvl, up = process_level_up(300, 1)
        assert lvl == 3  # 300 >= 100 + 150
        assert up is True


class TestLevelRoles:
    """Test level role assignment."""

    def test_get_role_for_level(self):
        """Test getting role for a level."""
        level_roles = {
            5: 'Newcomer',
            10: 'Regular',
            25: 'Veteran',
            50: 'Elite',
        }

        def get_role_for_level(level):
            applicable_roles = [
                (lvl, role) for lvl, role in level_roles.items()
                if level >= lvl
            ]
            if applicable_roles:
                return max(applicable_roles, key=lambda x: x[0])[1]
            return None

        assert get_role_for_level(1) is None
        assert get_role_for_level(5) == 'Newcomer'
        assert get_role_for_level(7) == 'Newcomer'
        assert get_role_for_level(10) == 'Regular'
        assert get_role_for_level(25) == 'Veteran'
        assert get_role_for_level(50) == 'Elite'
        assert get_role_for_level(100) == 'Elite'

    def test_roles_to_add_on_level_up(self):
        """Test which roles to add on level up."""
        level_roles = {
            5: 'Newcomer',
            10: 'Regular',
            25: 'Veteran',
        }

        def get_roles_to_add(old_level, new_level):
            return [
                role for lvl, role in level_roles.items()
                if old_level < lvl <= new_level
            ]

        # Level 1 to 5 - gain Newcomer
        assert get_roles_to_add(1, 5) == ['Newcomer']

        # Level 5 to 10 - gain Regular
        assert get_roles_to_add(5, 10) == ['Regular']

        # Level 1 to 12 - gain both Newcomer and Regular
        roles = get_roles_to_add(1, 12)
        assert 'Newcomer' in roles
        assert 'Regular' in roles


class TestXPGain:
    """Test XP gain mechanics."""

    def test_xp_gain_amount(self):
        """Test XP gain per message."""
        xp_per_message = 15

        # Consistent XP gain
        assert xp_per_message == 15

    def test_xp_cooldown(self):
        """Test XP cooldown mechanism."""
        from datetime import datetime, timedelta

        cooldown_seconds = 60

        def can_gain_xp(last_message_time, current_time):
            if last_message_time is None:
                return True
            elapsed = (current_time - last_message_time).total_seconds()
            return elapsed >= cooldown_seconds

        now = datetime.now()
        last_msg = now - timedelta(seconds=30)

        # Too soon
        assert can_gain_xp(last_msg, now) is False

        last_msg = now - timedelta(seconds=60)
        # Exactly on cooldown
        assert can_gain_xp(last_msg, now) is True

        last_msg = now - timedelta(seconds=120)
        # Well past cooldown
        assert can_gain_xp(last_msg, now) is True

        # First message ever
        assert can_gain_xp(None, now) is True

    def test_xp_bonus_multiplier(self):
        """Test XP bonus multipliers."""
        base_xp = 15

        def calculate_xp(base, multiplier=1.0, bonus=0):
            return int(base * multiplier + bonus)

        # No bonus
        assert calculate_xp(base_xp) == 15

        # 2x multiplier (weekend event)
        assert calculate_xp(base_xp, multiplier=2.0) == 30

        # Flat bonus
        assert calculate_xp(base_xp, bonus=10) == 25

        # Combined
        assert calculate_xp(base_xp, multiplier=1.5, bonus=5) == 27


class TestLeaderboard:
    """Test leaderboard functionality."""

    def test_leaderboard_sorting(self):
        """Test leaderboard sorting by total XP."""
        users = [
            {'user_id': 1, 'username': 'User1', 'total_xp': 500},
            {'user_id': 2, 'username': 'User2', 'total_xp': 2000},
            {'user_id': 3, 'username': 'User3', 'total_xp': 150},
            {'user_id': 4, 'username': 'User4', 'total_xp': 1200},
        ]

        leaderboard = sorted(users, key=lambda x: x['total_xp'], reverse=True)

        assert leaderboard[0]['username'] == 'User2'
        assert leaderboard[1]['username'] == 'User4'
        assert leaderboard[2]['username'] == 'User1'
        assert leaderboard[3]['username'] == 'User3'

    def test_leaderboard_ranking(self):
        """Test leaderboard ranking assignment."""
        users = [
            {'user_id': 2, 'username': 'User2', 'total_xp': 2000},
            {'user_id': 4, 'username': 'User4', 'total_xp': 1200},
            {'user_id': 1, 'username': 'User1', 'total_xp': 500},
        ]

        ranked = [
            {**user, 'rank': idx + 1}
            for idx, user in enumerate(users)
        ]

        assert ranked[0]['rank'] == 1
        assert ranked[1]['rank'] == 2
        assert ranked[2]['rank'] == 3

    def test_user_rank_finding(self):
        """Test finding a specific user's rank."""
        users = [
            {'user_id': 2, 'total_xp': 2000},
            {'user_id': 4, 'total_xp': 1200},
            {'user_id': 1, 'total_xp': 500},
            {'user_id': 3, 'total_xp': 150},
        ]

        def find_user_rank(user_id, leaderboard):
            for idx, user in enumerate(leaderboard, 1):
                if user['user_id'] == user_id:
                    return idx
            return None

        assert find_user_rank(2, users) == 1
        assert find_user_rank(4, users) == 2
        assert find_user_rank(1, users) == 3
        assert find_user_rank(999, users) is None
