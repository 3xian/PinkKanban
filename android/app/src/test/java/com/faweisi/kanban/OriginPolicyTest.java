package com.faweisi.kanban;

import org.junit.Test;
import static org.junit.Assert.*;

public class OriginPolicyTest {
    private final OriginPolicy policy = new OriginPolicy("https://kanban.faweisi.com", false);

    @Test public void navigationMatchesExactOrigin() {
        assertTrue(policy.isInternal("https://kanban.faweisi.com/#/board/1"));
        assertTrue(policy.isInternal("https://KANBAN.faweisi.com:443/"));
        for (String url : new String[]{"https://kanban.faweisi.com.evil.test/", "https://kanban.faweisi.com@evil.test/",
                "https://evil@kanban.faweisi.com/", "http://kanban.faweisi.com/", "https://kanban.faweisi.com:444/",
                "file:///etc/passwd", "javascript:alert(1)", "//kanban.faweisi.com/", "https://[", "about:blank"}) {
            assertFalse(url, policy.isInternal(url));
        }
    }

    @Test public void onlyAttachmentEndpointReceivesCredentials() {
        assertTrue(policy.isAttachment("https://kanban.faweisi.com/api/attachments/12/file?download=1"));
        assertFalse(policy.isAttachment("https://evil.test/api/attachments/12/file"));
        assertFalse(policy.isAttachment("https://kanban.faweisi.com/api/attachments/12/file/extra"));
        assertFalse(policy.isAttachment("https://kanban.faweisi.com/api/auth/me"));
        assertFalse(policy.isAttachment("https://kanban.faweisi.com/api/attachments/../file"));
    }

    @Test public void localHttpRequiresDebug() {
        assertTrue(new OriginPolicy("http://10.0.2.2:8000", true).isInternal("http://10.0.2.2:8000/#/"));
        assertThrows(IllegalArgumentException.class, () -> new OriginPolicy("http://10.0.2.2:8000", false));
        assertThrows(IllegalArgumentException.class, () -> new OriginPolicy("http://evil.test", true));
    }

    @Test public void externalLinksCannotLaunchArbitraryIntents() {
        assertTrue(policy.isExternal("mailto:team@example.com"));
        assertTrue(policy.isExternal("https://example.com/docs"));
        assertFalse(policy.isExternal("intent://example#Intent;scheme=evil;end"));
        assertFalse(policy.isExternal("content://private/file"));
        assertFalse(policy.isExternal("javascript:alert(1)"));
    }
}
