# Casino Bookmarks Manager

A web application to manage and open multiple casino websites at once using custom subdomains.

## Features

- **Admin Interface**: Web-based UI to manage subdomains and URLs
- **Dynamic Subdomains**: Each subdomain opens its configured list of websites
- **One-Click Opening**: Visit a subdomain to open all sites in new tabs automatically
- **User-Friendly Management**: Add, remove, and reorder URLs with a simple interface
- **Secure**: Password-protected admin panel

## Setup Instructions

### 1. Create Directory Structure

On your server, create a directory for the application:

```bash
sudo mkdir -p /mnt/docker-data/compose/casino-bookmarks
cd /mnt/docker-data/compose/casino-bookmarks
```

### 2. Upload Files

Upload all the application files to this directory:
- app.py
- Dockerfile
- docker-compose.yml
- requirements.txt
- templates/ (entire directory)

### 3. Create Data Directory

```bash
sudo mkdir -p data
sudo chmod 755 data
```

### 4. Build and Start

```bash
sudo docker compose up -d --build
```

### 5. Configure DNS

For each subdomain you want to use, add a DNS A record pointing to your server:

**Required DNS record for admin:**
- `casinobookmarks.dougshipe.com` → Your Server IP

**Example subdomain records:**
- `blackjack.dougshipe.com` → Your Server IP
- `poker.dougshipe.com` → Your Server IP
- `slots.dougshipe.com` → Your Server IP

### 6. Access Admin Panel

1. Visit: https://casinobookmarks.dougshipe.com
2. Login with:
   - Username: `doug`
   - Password: `Casinos4$Please`

## Usage

### Creating a Subdomain

1. Log into the admin panel
2. Enter a subdomain name (e.g., "blackjack")
3. Click "Create"
4. Add the corresponding DNS record
5. Click "Edit URLs" to add websites

### Adding URLs to a Subdomain

1. Click "Edit URLs" for the subdomain
2. Enter the full URL (including https://)
3. Click "Add URL"
4. Repeat for all sites you want to open
5. Use the ↑↓ buttons to reorder URLs

### Opening Sites

Simply visit the subdomain URL (e.g., https://blackjack.dougshipe.com) and all configured sites will open in new tabs.

## Troubleshooting

### Pop-up Blocker

If your browser blocks the automatic opening:
1. Click "Allow pop-ups" when prompted
2. Or click the "Open All Sites Manually" button

### Container Logs

```bash
sudo docker logs casino-bookmarks
```

### Restart Container

```bash
cd /mnt/docker-data/compose/casino-bookmarks
sudo docker compose restart
```

### Update Application

```bash
cd /mnt/docker-data/compose/casino-bookmarks
sudo docker compose down
# Upload new files
sudo docker compose up -d --build
```

## Security Notes

- Admin panel is password-protected
- Change the SECRET_KEY in docker-compose.yml for production
- SSL certificates are automatically managed by Traefik via Cloudflare
- Database is stored in the ./data volume

## File Structure

```
casino-bookmarks/
├── app.py                  # Main Flask application
├── Dockerfile              # Container build instructions
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
├── templates/              # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── admin.html
│   ├── edit_subdomain.html
│   ├── opener.html
│   ├── subdomain_not_found.html
│   └── no_urls.html
└── data/                   # SQLite database (created on first run)
    └── bookmarks.db
```

## Technical Details

- **Framework**: Flask (Python)
- **Database**: SQLite
- **Reverse Proxy**: Traefik
- **SSL**: Cloudflare DNS Challenge
- **Authentication**: Werkzeug password hashing
