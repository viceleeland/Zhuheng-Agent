import org.changwei.mobile.ServerPolicy;

/** 不依赖 Android 框架的真实 URL 边界测试。 */
public class ServerPolicyTest {
    private static int checks;
    private static void check(boolean result) {
        checks++;
        if (!result) throw new AssertionError("Check " + checks);
    }
    private static void rejected(String value) {
        try { ServerPolicy.normalize(value); throw new AssertionError("Accepted unsafe server"); }
        catch (IllegalArgumentException expected) { checks++; }
    }
    public static void main(String[] args) {
        check(ServerPolicy.normalize("HTTPS://Example.COM:443/").equals("https://example.com"));
        check(ServerPolicy.normalize("https://example.com:8443").equals("https://example.com:8443"));
        for (String value : new String[]{"http://example.com", "javascript:alert(1)", "file:///tmp/x", "https://user:pass@example.com", "https://example.com/path", "https://example.com?key=x", "https://example.com#token", "https://example.com:0", "https://example.com:65536", "https://", "https://example.com\\evil"}) rejected(value);
        check(ServerPolicy.sameOrigin("https://example.com", "https://example.com/api/download?item=1"));
        check(ServerPolicy.sameOrigin("https://example.com", "https://EXAMPLE.com:443/changwei"));
        check(!ServerPolicy.sameOrigin("https://example.com", "https://example.com.evil.test/"));
        check(!ServerPolicy.sameOrigin("https://example.com", "https://example.com@evil.test/"));
        check(!ServerPolicy.sameOrigin("https://example.com", "https://example.com:8443/"));
        check(!ServerPolicy.sameOrigin("https://example.com", "http://example.com/"));
        check(!ServerPolicy.sameOrigin("https://example.com", null));
        check(ServerPolicy.filename("../bad\\name\n.docx").equals(".._bad_name_.docx"));
        check(ServerPolicy.filename("").equals("工程成果.docx"));
        System.out.println("ServerPolicy: " + checks + " checks passed");
    }
}
