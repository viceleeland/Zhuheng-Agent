package org.changwei.mobile;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** 仅接受一个不带凭据的 HTTPS 服务源，避免站点切换携带登录态。 */
public final class ServerPolicy {
    public static final String DEFAULT_SERVER = "https://viceleeyoung.tail3f46fb.ts.net";

    public static String normalize(String input) {
        try {
            URI uri = new URI(input.trim());
            String path = uri.getRawPath();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                    || uri.getRawFragment() != null || (path != null && !path.isEmpty() && !path.equals("/"))
                    || uri.getPort() == 0 || uri.getPort() > 65535 || uri.getPort() < -1) {
                throw new IllegalArgumentException("请输入 HTTPS 域名，可带端口，不含路径、账号或参数。");
            }
            String host = uri.getHost().toLowerCase(Locale.ROOT);
            int port = uri.getPort();
            return "https://" + host + (port == -1 || port == 443 ? "" : ":" + port);
        } catch (URISyntaxException | NullPointerException error) {
            throw new IllegalArgumentException("请输入有效的 HTTPS 服务地址。");
        }
    }

    public static boolean sameOrigin(String server, String url) {
        try {
            URI uri = new URI(url);
            if (uri.getRawUserInfo() != null || uri.getHost() == null) return false;
            return normalize(uri.getScheme() + "://" + uri.getRawAuthority()).equals(server);
        } catch (IllegalArgumentException | URISyntaxException | NullPointerException error) {
            return false;
        }
    }

    public static String filename(String input) {
        String safe = input == null ? "" : input.replaceAll("[\\\\/\\p{Cntrl}:*?\"<>|]", "_").trim();
        if (safe.isEmpty() || safe.equals(".") || safe.equals("..")) safe = "工程成果.docx";
        return safe.length() > 120 ? safe.substring(0, 110) + ".docx" : safe;
    }
}
