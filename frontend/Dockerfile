FROM node:20-alpine AS builder

WORKDIR /app

# Copy package info and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the application
COPY . .

# Pass VITE_API_URL argument to the build step
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

# Build the frontend
RUN npm run build

# Stage 2: Serve the built frontend with Nginx
FROM nginx:alpine

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Optional: Add custom nginx configuration if needed, using default for now
# which serves index.html and static assets.

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
