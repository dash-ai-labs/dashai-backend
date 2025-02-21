![dashai-backend](https://socialify.git.ci/dash-ai-labs/dashai-backend/image?forks=1&issues=1&logo=https%3A%2F%2Fgetdash.ai%2Fbig_logo.png&name=1&owner=1&pattern=Charlie+Brown&pulls=1&stargazers=1&theme=Dark)

<p align="center"><b>Supercharge your email productivity</b></p>


> [!WARNING]
>
> 🚧 Work in Progress 🚧
> 
> This project is still in its early stages, it's rough around the edges. 
>
> We're building in public because that's the best way to make something great. Each bug report shows us what to fix. Each issue points to what matters.
>
> If you like seeing ideas grow from raw to remarkable, stick around. Your feedback shapes what this becomes.

![GitHub last commit](https://img.shields.io/github/last-commit/dash-ai-labs/dashai-backend)
[![](https://dcbadge.limes.pink/api/server/BbDjwtf9sK)](https://discord.gg/BbDjwtf9sK)


## Installation

## Tech Stack

Dash AI is built with modern and reliable technologies:

- **Frontend**: Svelte, TypeScript, TailwindCSS, Shadcn UI, Skeleton UI
- **Backend**: Python, FastAPI, SQLAlchemy ORM, Celery
- **Database**: PostgreSQL, Redis, Pinecone Vector Database
- **AI**: OpenAI, XAI
- **Authentication**: Google OAuth

## Getting Started

### Prerequisites


Before running the application, you'll need to set up several services and environment variables:

1. **Setup Local Services with Dev Container and Docker**

   - Make sure you have [Docker](https://docs.docker.com/get-docker/), [NodeJS](https://nodejs.org/en/download/), and [npm](https://www.npmjs.com/get-npm) installed.
   - Open codebase as a container in [VSCode](https://code.visualstudio.com/) or your favorite VSCode fork.
   - Run the following commands in order to populate your dependencies and setup docker

     ```
     pip install -r requirements.txt -r requirements-dev.txt
     ./run_dev.sh
     ```


2. **Google OAuth Setup**

   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a new project
   - Add the following APIs in your Google Cloud Project: [People API](https://console.cloud.google.com/apis/library/people.googleapis.com), [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
     - Use the links above and click 'Enable' or
     - Go to 'APIs and Services' > 'Enable APIs and Services' > Search for 'Google People API' and click 'Enable'
     - Go to 'APIs and Services' > 'Enable APIs and Services' > Search for 'Gmail API' and click 'Enable'
   - Enable the Google OAuth2 API
   - Create OAuth 2.0 credentials (Web application type)
   - Add authorized redirect URIs:
     - Development:
       - `http://localhost:8080/oauth_callback`
     - Production:
       - `https://your-production-url/oauth_callback`
   - Add to `.env`:

     ```env
        POSTGRES_URL=
        SECRET_KEY=
        GOOGLE_REDIRECT_URI=
        GOOGLE_CLIENT_CONFIG=
        CELERY_BROKER_URL=
        CELERY_RESULT_BACKEND=
        STAGE=
        XAI_API_KEY=
        OPENAI_API_KEY=
        PINECONE_API_KEY=
     ```

   - Add yourself as a test user:

     - Go to [`Audience`](https://console.cloud.google.com/auth/audience)
     - Under 'Test users' click 'Add Users'
     - Add your email and click 'Save'

> [!WARNING]
> The `GOOGLE_REDIRECT_URI` must match **exactly** what you configure in the Google Cloud Console, including the protocol (http/https), domain, and path - these are provided above.


### Environment Variables

Copy `.env.example` to `.env` and configure the following variables:

```env
POSTGRES_URL=         # Connection string for the PostgreSQL database (e.g., "postgresql://user:pass@host:port/db").
SECRET_KEY=           # Secret key for cryptographic operations and session management.
GOOGLE_REDIRECT_URI=  # URL where Google redirects after successful OAuth authentication.
GOOGLE_CLIENT_CONFIG= # JSON configuration detailing Google OAuth client credentials.
CELERY_BROKER_URL=    # URL for the Celery broker used to manage task queues.
CELERY_RESULT_BACKEND= # URL for storing the results of Celery tasks.
STAGE=                # Environment stage indicator (e.g., dev, staging, production).
XAI_API_KEY=          # API key for accessing the XAI services.
OPENAI_API_KEY=       # API key for interacting with OpenAI's services.
PINECONE_API_KEY=     # API key for integrating with the Pinecone vector database.
```

### Update the PostgreSQL database accordingly

Alembic will apply the schema migrations set in `.env`

```bash
alembic upgrade head
```


### Running Locally

Run the development server:

```bash
    ./run_dev.sh
```
