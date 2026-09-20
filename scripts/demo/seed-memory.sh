#!/bin/bash
# Pre-seed episodic memory with a previous ConfigMap fix
mkdir -p .prash
cat > .prash/memory.json << 'EOF'
{
  "similar_fixes": [
    {
      "category": "runtime",
      "confidence": 0.92,
      "problem_summary": "checkout-api CrashLoopBackOff: container cannot reach database because ConfigMap DATABASE_HOST points to nonexistent host 'postgres-wrong'",
      "root_cause": "ConfigMap checkout-api-config has DATABASE_HOST=postgres-wrong, but the postgres service is named 'postgres'",
      "fix_description": "Patch ConfigMap checkout-api-config to set DATABASE_HOST=postgres, then restart the deployment",
      "files_changed": [
        {
          "path": "configmap/checkout-api-config",
          "key": "DATABASE_HOST",
          "old": "postgres-wrong",
          "new": "postgres"
        }
      ],
      "error_signature": "CrashLoopBackOff:checkout-api:configmap-database-host",
      "verified_at": "2026-09-19T22:00:00Z"
    }
  ],
  "repeated_error_signatures": [
    {
      "error_signature": "CrashLoopBackOff:checkout-api:configmap-database-host",
      "count": 1,
      "last_category": "runtime",
      "last_status": "verified"
    }
  ],
  "category_outcomes": {
    "runtime": {
      "attempts": 1,
      "verified": 1,
      "exhausted": 0,
      "verified_rate": 1.0
    }
  }
}
EOF
echo "✅ Episodic memory seeded with previous ConfigMap fix at .prash/memory.json"
