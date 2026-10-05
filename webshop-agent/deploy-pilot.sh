#!/bin/bash
# Deploy a pilot webshop agent instance to Railway
# Usage: ./deploy-pilot.sh PILOT_NAME SHOP_KIND SHOP_DOMAIN SHOP_TOKEN [SHOP_KEY] [SHOP_SECRET]
# Example: ./deploy-pilot.sh kozmetika-anna shoprenter example.shoprenter.hu token_xyz
# Example: ./deploy-pilot.sh salon-budapest woocommerce https://salon.hu key_abc secret_xyz

set -e

PILOT_NAME="${1:?Usage: deploy-pilot.sh PILOT_NAME SHOP_KIND SHOP_DOMAIN SHOP_TOKEN [SHOP_KEY] [SHOP_SECRET]}"
SHOP_KIND="${2:?Shop kind required: shopify|woocommerce|shoprenter}"
SHOP_DOMAIN="${3:?Shop domain required}"
SHOP_TOKEN="${4:?Shop token/key required}"
SHOP_KEY="${5:-}"
SHOP_SECRET="${6:-}"

# Normalize names
PILOT_SAFE=$(echo "$PILOT_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | sed 's/[^a-z0-9-]//g')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
INSTANCE_NAME="aximbra-pilot-${PILOT_SAFE}-${TIMESTAMP:0:8}"

echo "🚀 Deploying pilot: $PILOT_NAME"
echo "   Platform: $SHOP_KIND"
echo "   Instance: $INSTANCE_NAME"
echo ""

# Validate shop kind
case "$SHOP_KIND" in
  shopify|woocommerce|shoprenter)
    ;;
  *)
    echo "❌ Unknown shop kind: $SHOP_KIND"
    echo "   Supported: shopify, woocommerce, shoprenter"
    exit 1
    ;;
esac

# Validate Shopify setup
if [ "$SHOP_KIND" = "shopify" ]; then
  if [ -z "$SHOP_TOKEN" ]; then
    echo "❌ Shopify requires token"
    exit 1
  fi
  if [[ ! "$SHOP_DOMAIN" =~ \.myshopify\.com$ ]]; then
    echo "⚠️  Warning: domain doesn't look like a Shopify store"
    echo "   Expected format: example.myshopify.com"
  fi
fi

# Validate WooCommerce setup
if [ "$SHOP_KIND" = "woocommerce" ]; then
  if [ -z "$SHOP_KEY" ] || [ -z "$SHOP_SECRET" ]; then
    echo "❌ WooCommerce requires both key and secret"
    exit 1
  fi
  if [[ ! "$SHOP_DOMAIN" =~ ^https?:// ]]; then
    echo "⚠️  Assuming https:// for WooCommerce domain"
    SHOP_DOMAIN="https://$SHOP_DOMAIN"
  fi
fi

# Validate Shoprenter setup
if [ "$SHOP_KIND" = "shoprenter" ]; then
  if [ -z "$SHOP_TOKEN" ]; then
    echo "❌ Shoprenter requires token"
    exit 1
  fi
  if [[ ! "$SHOP_DOMAIN" =~ \.shoprenter\.hu$ ]]; then
    echo "⚠️  Warning: domain doesn't look like a Shoprenter store"
    echo "   Expected format: example.shoprenter.hu"
  fi
fi

echo "✅ Validation passed"
echo ""

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
  echo "❌ Railway CLI not found. Install it: npm install -g @railway/cli"
  echo "   Then: railway login"
  exit 1
fi

echo "📦 Building and deploying..."
echo ""

# Create environment file
ENV_FILE=".env.pilot-${PILOT_SAFE}"
cat > "$ENV_FILE" << EOF
# Pilot: $PILOT_NAME
# Generated: $(date)

SHOP_KIND=$SHOP_KIND
AGENT_TOKEN=$(head -c 32 /dev/urandom | base64 | tr -d '+/=' | cut -c 1-24)
SHOP_NAME=$PILOT_NAME
DEMO_PER_HOUR=50
DEMO_PER_DAY_TOTAL=1000
EOF

# Add platform-specific env vars
case "$SHOP_KIND" in
  shopify)
    cat >> "$ENV_FILE" << EOF
SHOPIFY_DOMAIN=$SHOP_DOMAIN
SHOPIFY_TOKEN=$SHOP_TOKEN
EOF
    ;;
  woocommerce)
    cat >> "$ENV_FILE" << EOF
WOO_URL=$SHOP_DOMAIN
WOO_KEY=$SHOP_KEY
WOO_SECRET=$SHOP_SECRET
EOF
    ;;
  shoprenter)
    cat >> "$ENV_FILE" << EOF
SHOPRENTER_DOMAIN=$SHOP_DOMAIN
SHOPRENTER_TOKEN=$SHOP_TOKEN
EOF
    ;;
esac

# Add database volume note
cat >> "$ENV_FILE" << EOF

# Note: This pilot runs in isolation. To persist data across restarts,
# attach a Railway volume at /data and set SALES_DB_PATH=/data/sales.db
EOF

echo "📝 Environment file created: $ENV_FILE"
echo "   AGENT_TOKEN: $(grep AGENT_TOKEN "$ENV_FILE" | cut -d= -f2)"
echo ""

# Summary
echo "🎯 Next steps:"
echo ""
echo "1. Review the environment file:"
echo "   cat $ENV_FILE"
echo ""
echo "2. Deploy to Railway (requires CLI login):"
echo "   railway up"
echo ""
echo "3. Test the pilot:"
echo "   curl -X POST https://<your-railway-url>/api/demo/reply \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"from_email\": \"test@example.com\", \"subject\": \"Hol a rendelésem?\", \"body\": \"Rendelésszám: 1234\"}'"
echo ""
echo "4. Authenticate requests:"
echo "   curl -X POST https://<your-railway-url>/api/reply \\"
echo "     -H 'X-Agent-Token: $(grep AGENT_TOKEN "$ENV_FILE" | cut -d= -f2)' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{...}'"
echo ""
echo "5. Share pilot dashboard:"
echo "   Dashboard URL: https://aximbra-sales-production.up.railway.app/?pilot=$PILOT_SAFE"
echo "   (Ask Péter for access)"
echo ""
echo "✨ Pilot '$PILOT_NAME' ready to deploy!"
