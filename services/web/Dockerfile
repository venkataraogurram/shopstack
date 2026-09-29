# syntax=docker/dockerfile:1
# Stage 1: stamp the build version into the page (needs write access)
FROM public.ecr.aws/docker/library/alpine:3.20 AS build
ARG APP_VERSION=dev
COPY public/ /site/
RUN sed -i "s/__APP_VERSION__/${APP_VERSION}/" /site/index.html

# Stage 2: unprivileged Nginx (UID 101, port 8080, writes only to /tmp), which
# satisfies the "restricted" Pod Security Standard.
FROM public.ecr.aws/nginx/nginx-unprivileged:1.27-alpine
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /site/ /usr/share/nginx/html/
EXPOSE 8080
