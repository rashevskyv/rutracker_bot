# Project Overview

This project appears to be a Python-based Telegram bot designed to monitor the torrent tracker Rutracker. It seems to fetch updates from an RSS feed, parse tracker data, and send notifications via Telegram. The bot may also utilize various APIs for additional functionalities, including AI-powered validation, YouTube search, and translation services.

## Core Technologies

*   **Language:** Python
*   **Key Libraries:**
    *   `requests`: For making HTTP requests to fetch web pages and data.
    *   `beautifulsoup4`: For parsing HTML content, likely from Rutracker pages.
    *   `feedparser`: For parsing RSS/Atom feeds to get the latest updates.
    *   `pyTelegramBotAPI`: For interacting with the Telegram Bot API to send messages.
    *   `openai`: Suggests integration with OpenAI's API, possibly for content validation or generation.
    *   `google-api-python-client`, `google-cloud-translate`: Indicates use of Google APIs for services like translation.
    *   `yt-dlp`: A YouTube downloader, likely used for fetching videos or metadata.

## Project Structure

The project is structured into several Python modules, each with a specific responsibility:

*   `main.py`: The main entry point of the application.
*   `feed_handler.py`: Handles fetching and parsing of the RSS feed.
*   `tracker_parser.py`: Parses the HTML content of torrent pages.
*   `telegram_sender.py`: Manages sending messages to Telegram.
*   `settings_loader.py`: Loads and manages application settings from `settings.json`.
*   `ai_validator.py`, `youtube_search.py`, `translation.py`: Modules for integrating with external services.
*   `titledb_manager.py`: Manages a local database of titles.

## Building and Running

**Prerequisites:**

*   Python 3.x
*   `pip` for installing dependencies.

**Installation:**

1.  Install the required Python packages:

    ```bash
    pip install -r requirements.txt
    ```

**Configuration:**

1.  Create a `settings.json` file based on the required settings in the source code. This file will likely need to contain API keys for Telegram, OpenAI, and Google services, as well as other configuration options.

**Running the bot:**

*   The `run.bat` file seems to be outdated and contains an incorrect path and entry point. To run the bot, you should execute the `main.py` script:

    ```bash
    python main.py
    ```

    *TODO: The exact execution command might need adjustments based on the contents of `main.py` and the required environment variables.*

## Development Conventions

*   The code seems to be organized into modules with clear responsibilities.
*   There are some test files (e.g., `test_telegram_sender.py`), which suggests that testing is part of the development process.
*   The use of a `settings.json` file for configuration allows for easy customization without modifying the source code.
