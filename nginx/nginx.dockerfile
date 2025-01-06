
# Use the official Nginx image as the base
FROM nginx:latest

# Remove the default Nginx configuration file from container
RUN rm /etc/nginx/conf.d/default.conf

# Copy our custom Nginx configuration into the container
COPY nginx.conf /etc/nginx/conf.d

# Expose port 80 to allow external access to the container's port 80
EXPOSE 80

#run command on container create which starts nginx. nginx works as a foreground process since docker considers daemon processes as "not running", hence it shutsdown the container
CMD ["nginx", "-g", "daemon off;"]
