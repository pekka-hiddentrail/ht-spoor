# ROADMAP.md §5.1 archetype bench — Sauce Demo, built from a pinned source commit.
#
# No official or trustworthy prebuilt image exists for the Sauce Labs sample
# storefront, so we build the static React (Vite) single-page app from a pinned
# commit of github.com/saucelabs/sample-app-web and serve it with nginx. Pinning
# the exact commit (not a moving branch) keeps the fixture deterministic, the same
# way the Juice Shop service pins an image tag.
#
# Why this app earns a place on the bench: it is architecturally unlike Juice Shop
# (a different SPA), and — unlike Juice Shop — it is login-gated. Its inventory is
# reachable only with an authenticated session, so it is the first real-world proof
# of bring-your-own-session (§2h) end to end, and a second data point that the
# generic tiers are not tailored to any one site (§0).
ARG SAMPLE_APP_SHA=60fdd634bb111c092282fa07977513a0a7765593

FROM node:24.9.0-alpine AS build
ARG SAMPLE_APP_SHA
# Disable husky's git hooks install; there is no git repo in the build context and
# the hooks are irrelevant to a production build.
ENV HUSKY=0
WORKDIR /app
# ADD does not auto-extract a *remote* tarball, so fetch then extract explicitly.
ADD https://github.com/saucelabs/sample-app-web/archive/${SAMPLE_APP_SHA}.tar.gz /tmp/src.tar.gz
RUN tar -xzf /tmp/src.tar.gz --strip-components=1 -C /app && rm /tmp/src.tar.gz
RUN npm ci
# Vite emits to "build" (build.outDir in vite.config.js), not the default "dist".
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
