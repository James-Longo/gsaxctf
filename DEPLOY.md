# Deployment Guide for gsaxctf.com

## 1. Setup GitHub Repository
1. Go to **[GitHub.com/new](https://github.com/new)** and create a new repository (e.g., `track-dashboard`).
2. Make it **Private** (recommended since it includes your database database).

## 2. Push Code
Run these commands in your terminal to upload your code:

```bash
# Initialize command
git init
git add .
git commit -m "Initial commit of Track Dashboard"

# Link to your new GitHub repo
git remote add origin https://github.com/YOUR_USERNAME/track-dashboard.git
git branch -M main
git push -u origin main
```

## 3. Deployment on Vercel
1. Go to **[Vercel.com](https://vercel.com)** and Sign Up/Login.
2. Click **"Add New..."** -> **"Project"**.
3. Import your `track-dashboard` repository.
4. **Configure Project**:
   - **Framework Preset**: Vite
   - **Root Directory**: Click "Edit" and select `ui` folder.
   - **Build Command**: `npm run build` (Default)
   - **Output Directory**: `dist` (Default)
5. Click **Deploy**.

## 4. Connect Domain
1. Once deployed, go to the Vercel Project Dashboard.
2. Click **Settings** -> **Domains**.
3. Enter `gsaxctf.com` and click Add.
4. Follow the instructions to update your DNS records (usually adding an A record or CNAME) at your domain registrar.

## 5. Automation (Optional)
Your scraper is set up to run **every Monday at 6am EST** via GitHub Actions.
- It will automatically scrape new results, update `data.json`, and commit it.
- Vercel will detect the commit and automatically re-deploy the site with the new data.
