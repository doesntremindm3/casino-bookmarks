#!/bin/bash

# Casino Bookmarks - Deployment Script
# This script helps deploy the application to your server

set -e

echo "================================"
echo "Casino Bookmarks Deployment"
echo "================================"
echo ""

# Configuration
INSTALL_DIR="/mnt/docker-data/compose/casino-bookmarks"
BACKUP_DIR="/mnt/docker-data/compose/casino-bookmarks-backup-$(date +%Y%m%d-%H%M%S)"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo"
    exit 1
fi

echo "Installation directory: $INSTALL_DIR"
echo ""

# Backup existing installation if it exists
if [ -d "$INSTALL_DIR" ]; then
    echo "Existing installation found. Creating backup..."
    cp -r "$INSTALL_DIR" "$BACKUP_DIR"
    echo "Backup created at: $BACKUP_DIR"
    echo ""
    
    # Stop existing container
    echo "Stopping existing container..."
    cd "$INSTALL_DIR"
    docker compose down || true
    echo ""
fi

# Create directory structure
echo "Creating directory structure..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Create data directory with proper permissions
mkdir -p data
chmod 755 data

echo ""
echo "================================"
echo "Files should now be uploaded to:"
echo "$INSTALL_DIR"
echo ""
echo "Required files:"
echo "  - app.py"
echo "  - Dockerfile"
echo "  - docker-compose.yml"
echo "  - requirements.txt"
echo "  - templates/ (directory)"
echo "================================"
echo ""

read -p "Have you uploaded all files? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please upload files and run this script again."
    exit 1
fi

# Build and start
echo ""
echo "Building and starting containers..."
docker compose up -d --build

echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Add DNS record: casinobookmarks.dougshipe.com -> Your Server IP"
echo "2. Visit: https://casinobookmarks.dougshipe.com"
echo "3. Login with:"
echo "   Username: doug"
echo "   Password: Casinos4\$Please"
echo ""
echo "To view logs:"
echo "  sudo docker logs -f casino-bookmarks"
echo ""
echo "To restart:"
echo "  cd $INSTALL_DIR && sudo docker compose restart"
echo ""
