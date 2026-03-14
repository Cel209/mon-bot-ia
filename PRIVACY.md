# Privacy Policy

**Effective Date: March 2026**

This Privacy Policy describes how our Discord application collects, utilizes, and protects user data.

### 1. Data Collection and Storage
The application stores the absolute minimum amount of data required for its features. Data is stored locally in JSON format (`gacha.json`, `vip_data.json`, `stats.json`, `notifs.json`).
* **Discord User IDs:** Collected to maintain individual virtual economy profiles. This includes tracking Gacha points, manual tickets, active virtual loans, loan multipliers, and AI usage limits (tokens).
* **Discord Guild and Channel IDs:** Collected strictly for server administrators who enable automated notifications (e.g., the Steam free games tracker) or use the persistent support ticket panel.

### 2. Message Content Processing (Strictly Passthrough)
To function as a conversational AI, the application requires access to message content in the channels it operates in.
* **No Persistent Storage:** Message content is processed in RAM to generate a response and is immediately discarded. **We do not log, record, or store any message content, attachments, or conversation history in our databases.**
* **API Transmission:** Message content is securely transmitted to third-party APIs (Google Gemini API for text processing, Hugging Face API for image generation) solely for the purpose of fulfilling the user's request. 

### 3. Third-Party Services
By interacting with the application, your prompts are subject to the privacy policies of our API providers:
* **Google (Gemini API):** Used for natural language processing and text generation.
* **Hugging Face:** Used for text-to-image and text-to-video generation features.
* **GamerPower API:** Used passively by the bot to fetch free game data (no user data is sent to this API).

### 4. Data Sharing and Protection
We do not sell, rent, or share User IDs or economy data with advertisers or unauthorized third parties. Data is contained within the host server's local environment.

### 5. Data Deletion and User Rights
Users have the right to request the complete removal of their data. To have your User ID and associated economy data wiped from the JSON databases, you must open a support ticket within the bot's host server or open an issue on this GitHub repository. Requests will be executed within 48 hours.
