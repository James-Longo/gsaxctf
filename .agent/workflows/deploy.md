---
description: How to deploy the application to Vercel
---

# Deployment Workflow

To deploy the latest changes to the production site (gsaxctf.com):

// turbo
1. **Prepare Data (if backend/data changed)**
   If you have updated the scraper or added new results, ensure the local database is synced and exported to the frontend data file:
   ```powershell
   python backend/export_for_web.py
   ```

2. **Build and Deploy**
   The Vercel project is linked to the root of this repository. Even though the frontend code is in the `ui` directory, the deployment command **MUST** be run from the **root directory** to ensure the production alias is applied correctly.

   // turbo
   ```powershell
   npx vercel --prod
   ```

   *Note: Do not run the production deployment from inside the `ui` directory unless specifically instructed, as it may not target the correct project alias.*
