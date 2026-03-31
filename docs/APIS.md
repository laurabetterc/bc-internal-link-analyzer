# APIs & External Services — Internal Link Analyzer

## Gemini API (Google)

- **Model**: Gemini 2.5 Flash (`gemini-2.5-flash`)
- **What for**: Semantic analysis of pages, finding linking opportunities, cocoon detection, generating anchor text suggestions
- **Pricing**: Free tier available (15 RPM, 1M tokens/day). Paid tier: $0.10/1M input tokens, $0.40/1M output tokens. See https://ai.google.dev/pricing for current rates.
- **Setup steps**:
  1. Go to https://aistudio.google.com/apikey
  2. Sign in with your Google account
  3. Click "Create API Key"
  4. Copy the key
  5. Set it as an environment variable before running the app:
     ```bash
     export GEMINI_API_KEY=your-key-here
     streamlit run src/app.py
     ```
- **Key status**: Required for AI features (cocoon detection, link recommendations, anchor suggestions). The tool works without it — you'll still get link audit, PageRank, and priority URL health — but AI features will be disabled.
- **Rate limits**: Free tier: 15 requests/minute, 1M tokens/day. Sufficient for our use case (2-6 API calls per analysis).
- **Cost estimate**: Most analyses should stay within the free tier. If paid: ~$0.01-0.05 per analysis (vs. ~$0.50-2.00 with Claude API).

## No Other External Services (v1)

v1 has no other API dependencies. All data comes from user-uploaded CSV files.
