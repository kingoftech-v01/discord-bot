# Contributing Guide

Thank you for your interest in contributing to Discord Bot Pro!

## Getting Started

### Prerequisites

- Python 3.10+
- Git
- Discord account for testing

### Development Setup

1. **Fork the repository**

2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR-USERNAME/discord-bot.git
   cd discord-bot
   ```

3. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

5. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

6. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your test bot token
   ```

## Development Workflow

### Branch Naming

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation
- `refactor/` - Code refactoring
- `test/` - Test additions

Examples:
- `feature/add-music-commands`
- `fix/leveling-xp-calculation`
- `docs/api-examples`

### Making Changes

1. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

3. **Run tests**
   ```bash
   pytest
   ```

4. **Run linting**
   ```bash
   flake8 .
   black --check .
   ```

5. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

6. **Push to your fork**
   ```bash
   git push origin feature/your-feature-name
   ```

7. **Create a Pull Request**

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Formatting (no code change)
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance

Examples:
```
feat: add trivia leaderboard command
fix: correct XP calculation for level up
docs: update API authentication guide
refactor: simplify database connection logic
test: add tests for moderation cog
```

## Code Style

### Python

- Follow [PEP 8](https://pep8.org/)
- Use [Black](https://black.readthedocs.io/) for formatting
- Maximum line length: 88 characters
- Use type hints where appropriate

```python
# Good
async def get_user_level(user_id: int, guild_id: int) -> int:
    """Get the level of a user in a guild."""
    ...

# Bad
async def getUserLevel(userId, guildId):
    ...
```

### Documentation

- Use docstrings for all public functions
- Keep comments meaningful
- Update README when adding features

```python
async def add_xp(self, user_id: int, guild_id: int, amount: int) -> tuple[int, bool]:
    """
    Add XP to a user and check for level up.

    Args:
        user_id: Discord user ID
        guild_id: Discord guild ID
        amount: XP amount to add

    Returns:
        Tuple of (new_level, leveled_up)
    """
    ...
```

## Adding Features

### New Bot Command

1. Create or modify a cog in `cogs/`
2. Follow existing patterns
3. Add command documentation
4. Write tests

```python
@commands.command(name="mycommand")
@commands.cooldown(1, 5, commands.BucketType.user)
async def my_command(self, ctx: commands.Context, arg: str):
    """
    Description of your command.

    Usage: !mycommand <arg>
    Example: !mycommand hello
    """
    ...
```

### New API Endpoint

1. Add serializer in `dashboard/api/serializers.py`
2. Add view in `dashboard/api/views.py`
3. Register URL in `dashboard/api/urls.py`
4. Update API documentation
5. Write tests

### Database Changes

1. Update models in `utils/database.py` or `dashboard/core/models.py`
2. Create migration (Django):
   ```bash
   python manage.py makemigrations
   ```
3. Test migration rollback
4. Document changes

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific file
pytest tests/test_leveling.py

# With coverage
pytest --cov=.

# Verbose output
pytest -v
```

### Writing Tests

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_add_xp():
    """Test XP addition and level up."""
    db = MagicMock()
    db.get_user = AsyncMock(return_value={'level': 1, 'xp': 90})
    db.update_user = AsyncMock()

    result = await add_xp(db, user_id=123, guild_id=456, amount=15)

    assert result == (2, True)  # Level 2, leveled up
    db.update_user.assert_called_once()
```

### Test Categories

- `tests/test_bot/` - Bot command tests
- `tests/test_api/` - API endpoint tests
- `tests/test_database/` - Database operation tests
- `tests/test_integration/` - Integration tests

## Pull Request Guidelines

### Before Submitting

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactoring

## Testing
How was this tested?

## Screenshots (if applicable)

## Checklist
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] No breaking changes
```

### Review Process

1. Automated checks must pass
2. At least one maintainer approval required
3. Address review feedback
4. Squash commits if requested

## Reporting Issues

### Bug Reports

Include:
- Python version
- OS
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages/logs

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternatives considered

## Community

- Be respectful and inclusive
- Help others when possible
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md)

## Questions?

- Open an issue for questions
- Join our Discord server
- Check existing documentation

Thank you for contributing!
