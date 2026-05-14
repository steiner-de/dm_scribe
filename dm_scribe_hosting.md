# DM Scribe Hosting Guide

This guide explains how to deploy DM Scribe to the cloud so it runs 24/7 without requiring local execution. Users can add the bot to their Discord server via an invite link without any installation.

## Overview
Instead of running `python run.py` locally, your bot will run on a cloud platform. Users simply add the bot to their Discord server using an invite link, just like any other Discord bot.

## 1. Prepare Your Bot for Deployment

Before deploying, ensure your bot is production-ready:

- **Test locally**: Run `python run.py` and verify all commands work in a test Discord server.
- **Environment variables**: Your `.env` file should have the real `DISCORD_TOKEN`. For production, use the hosting platform's environment variable management instead of a local `.env` file.
- **Dependencies**: Your `requirements.txt` is already set up with all needed packages.
- **Ollama dependency**: Since you're using local Ollama, choose a hosting platform that supports running background processes or containers (Railway, DigitalOcean, etc.).

## 2. Choose a Hosting Platform

For a Python Discord bot, here are recommended options (all support free tiers for testing):

### Railway (Recommended)
- Easy Python deployment
- Supports Ollama via Docker
- Free tier available
- Automatic scaling
- Website: [railway.app](https://railway.app)

### Heroku
- Popular for Discord bots
- Good Python support
- Free tier (with limitations)
- May need to handle Ollama separately

### DigitalOcean App Platform
- Good for containerized apps
- Can run Ollama in a container
- Pay-as-you-go pricing

### AWS EC2 or Google Cloud Run
- More advanced, but powerful
- Better for production scaling

## 3. Deployment Steps (Using Railway as Example)

### Step 1: Create a Railway Account
1. Go to [railway.app](https://railway.app) and sign up.
2. Connect your GitHub account for easy deployment.

### Step 2: Deploy from GitHub
1. In Railway, click "New Project" > "Deploy from GitHub repo".
2. Select your `dm_scribe` repository.
3. Railway will automatically detect it's a Python app and use `requirements.txt`.

### Step 3: Configure Environment Variables
1. In Railway's project settings, add environment variables:
   - `DISCORD_TOKEN`: Your bot token from Discord Developer Portal
   - `OLLAMA_HOST`: If needed, set to `http://localhost:11434` (Railway can handle this)
2. Remove or ignore `.env` in your repo (ensure it's in `.gitignore`).

### Step 4: Handle Ollama

Since Ollama needs to run as a background service, use Railway's Docker support:

1. Create a `Dockerfile` in your repo root:
   ```dockerfile
   FROM python:3.11-slim

   # Install Ollama
   RUN apt-get update && apt-get install -y curl
   RUN curl -fsSL https://ollama.ai/install.sh | sh

   # Copy your app
   WORKDIR /app
   COPY . .

   # Install Python deps
   RUN pip install -r requirements.txt

   # Start Ollama and your bot
   CMD ollama serve & python run.py
   ```

2. Commit the `Dockerfile` to your GitHub repo.
3. Railway will automatically use it for deployment.

### Step 5: Deploy and Test
1. Railway will build and deploy automatically.
2. Check the logs to ensure the bot starts and Ollama is running.
3. Test by inviting the bot to a Discord server and running `!help`.

## 4. Make the Bot Discoverable

Once deployed:

### Update Discord Developer Portal
1. Go to your bot application at [Discord Developer Portal](https://discord.com/developers/applications).
2. Under "OAuth2" > "URL Generator", select the `bot` scope and permissions your bot needs:
   - `Send Messages`
   - `Connect` (voice)
   - `Speak` (voice)
   - `Read Message History`
3. Copy the generated invite URL.

### Share the Invite Link
- Users can click the invite URL to add the bot to their server.
- No local installation required—they just add it like any other Discord bot.
- Example link format: `https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=PERMISSIONS&scope=bot`

### Update Documentation
- Add the invite link to your README.
- Include setup instructions for users on how to use the bot in their server.

## 5. Maintenance and Scaling

### Monitoring
- Use Railway's logs to monitor bot activity.
- Check for errors related to Ollama or Discord connections.

### Updates
- Push changes to GitHub; Railway auto-deploys.
- No downtime during redeploy.

### Costs
- Start with free tiers, but monitor usage (especially with Ollama running continuously).
- Ollama is resource-intensive; consider costs as your usage grows.

### Security
- Keep your `DISCORD_TOKEN` secure—never commit it to GitHub.
- Use hosting platform's environment variable management.

## 6. Troubleshooting

### Bot Not Responding
- Check Railway logs for errors (e.g., missing token, Ollama not starting).
- Verify bot has correct Discord permissions in the server.

### Ollama Issues
- Ensure the hosting platform supports background processes or containers.
- Check if Ollama started correctly in the logs.
- Consider using a separate Ollama service if needed.

### Permission Errors
- Verify bot role has the required permissions in Discord server settings.
- Check that bot can access the notes channel and voice channels.

### Slow Summaries
- Ollama running on shared hosting may be slower than local.
- Consider upgrading hosting tier if performance is critical.

## 7. Alternative: Using a Separate Ollama Service

If you want to keep Ollama separate from the bot:

1. Deploy Ollama to a separate service (e.g., DigitalOcean, AWS).
2. Update your `OLLAMA_HOST` environment variable to point to the remote Ollama server.
3. The bot will connect to it via HTTP.

This allows you to scale each component independently.

## 8. Environment Variables Checklist

For deployment, ensure these are set in your hosting platform:

```
DISCORD_TOKEN=<your_bot_token>
TRANSCRIPTION_SERVICE=faster-whisper
WHISPER_MODEL=base
```

Optional:
```
OLLAMA_HOST=http://localhost:11434
```

## Next Steps

1. Choose a hosting platform.
2. Create a `Dockerfile` (if using Railway or Docker-based platforms).
3. Push changes to GitHub.
4. Deploy via your chosen platform.
5. Test the bot invite link in a test Discord server.
6. Share the invite link with users.

For questions or platform-specific issues, refer to your hosting platform's documentation.
