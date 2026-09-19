FROM mirror.gcr.io/library/nginx@sha256:48d6de146898643e53f6795420bd79340125c264905f4e8855310edc4a7ff1c7
COPY nginx.conf /etc/nginx/nginx.conf
COPY dist /usr/share/nginx/html
USER 101:101
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
LABEL org.opencontainers.image.title="Jiangqing web" org.opencontainers.image.version="0.2.0"
