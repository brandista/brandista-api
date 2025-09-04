

# Luo utils.js tiedosto
cat > src/lib/utils.js << 'EOF'
import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
EOF
