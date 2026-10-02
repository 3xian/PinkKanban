package com.faweisi.kanban;

import java.net.URI;
import java.util.Locale;

/** A single origin boundary shared by navigation and authenticated downloads. */
final class OriginPolicy {
    private final URI origin;

    OriginPolicy(String baseUrl, boolean debug) {
        origin = URI.create(baseUrl);
        String host = origin.getHost();
        boolean local = "localhost".equals(host) || "127.0.0.1".equals(host) || "10.0.2.2".equals(host);
        if (host == null || origin.getUserInfo() != null || origin.getQuery() != null ||
                origin.getFragment() != null || !(origin.getPath().isEmpty() || "/".equals(origin.getPath())) ||
                !("https".equals(origin.getScheme()) || (debug && local && "http".equals(origin.getScheme())))) {
            throw new IllegalArgumentException("Invalid server origin");
        }
    }

    boolean isInternal(String value) {
        try {
            URI uri = URI.create(value);
            return uri.getUserInfo() == null && origin.getScheme().equalsIgnoreCase(uri.getScheme()) &&
                    origin.getHost().equalsIgnoreCase(uri.getHost()) && port(origin) == port(uri);
        } catch (IllegalArgumentException | NullPointerException e) {
            return false;
        }
    }

    boolean isAttachment(String value) {
        if (!isInternal(value)) return false;
        return URI.create(value).getPath().matches("/api/attachments/[0-9]+/file");
    }

    boolean isExternal(String value) {
        try {
            String scheme = URI.create(value).getScheme();
            return scheme != null && switch (scheme.toLowerCase(Locale.ROOT)) {
                case "https", "http", "mailto", "tel" -> true;
                default -> false;
            };
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    private static int port(URI uri) {
        return uri.getPort() == -1 ? ("https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80) : uri.getPort();
    }
}
