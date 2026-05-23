# Running Sentinel Pulse - MongoDB Setup Options

Choose one of the three options below:

---

## Option 1: Local MongoDB (Recommended for Development)

### Install MongoDB
1. Download MongoDB Community Edition:
   https://www.mongodb.com/try/download/community

2. Select:
   - Version: 8.0 (or latest stable)
   - Platform: Windows
   - Package: MSI

3. Run the installer with default settings

### Start MongoDB
Open a new command prompt and run:
```powershell
mongod
```

Keep this window open while using Sentinel Pulse. MongoDB will listen on localhost:27017.

---

## Option 2: MongoDB Atlas Cloud (Free Tier, No Install)

### Create Free Cluster
1. Go to: https://www.mongodb.com/cloud/atlas/register
2. Create free account
3. Create free cluster (M0 tier, AWS/Google/Azure)
4. Create database user (username/password)
5. Network access: Add IP 0.0.0.0/0 (allows all)
6. Get connection string:
   - Click "Connect" → "Connect your application"
   - Copy the mongodb+srv://... string

### Create .env File
In the Sentinel Pulse folder (where SentinelPulse.exe is), create a file called `.env`:

```
MONGO_URL=mongodb+srv://username:password@cluster.xxx.mongodb.net/sentinel_pulse
CREDENTIAL_KEY=your-secret-key-here
```

Replace the values with your actual credentials.

---

## Option 3: Fresh Local Data Directory

Use a fresh local MongoDB data directory when you want a clean beta-test database without touching existing data.

### Use a Local MongoDB URL
Create or edit the `.env` file in the app folder:

```
MONGO_URL=mongodb://localhost:27017
DB_NAME=sentinelpulse_beta
```

### Important Notes
- Data persists in MongoDB until you drop the database
- Runtime JWT and credential encryption secrets are generated per device if not set
- Good for isolated beta testing

---

## Quick Reference

| Need | Solution |
|------|----------|
| Dev testing | Option 1 |
| Cloud/No install | Option 2 |
| Quick UI test | Option 3 |
| Production | Option 1 or 2 |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| "No connection could be made" | MongoDB not running - start mongod |
| "Auth failed" | Check username/password in .env |
| "Clean database" needed | Set a new DB_NAME or drop the existing MongoDB database |
