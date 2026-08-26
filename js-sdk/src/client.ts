diff --git a/js-sdk/src/client.ts b/js-sdk/src/client.ts
index 0000001..0000002 100644
--- a/js-sdk/src/client.ts
+++ b/js-sdk/src/client.ts
@@ -1,3 +1,5 @@
+// RIP-0301: Tip Credits + Atlas Land Economy client methods
+
 import {ApiClient} from './api';
+import {
+  TipCredit,
+  CreateTipRequest,
+  AtlasDeed,
+  RegisterAtlasParcelRequest,
+  TransferAtlasDeedRequest,
+  RIP0301BlockSummary,
+} from './types';
+
+// -----------------------------------------------------------------------
+// RIP-0301: Tip Credits + Atlas Land Economy
+// -----------------------------------------------------------------------
+
+export class RIP0301Client {
+  constructor(private client: ApiClient) {}
+
+  // --- Tip Credits ---
+
+  async createTip(req: CreateTipRequest): Promise<TipCredit | null> {
+    return this.client.post('/rip0301/tip', req);
+  }
+
+  async getTipCredits(receiver: string): Promise<TipCredit[]> {
+    return this.client.get(`/rip0301/tips/${receiver}`);
+  }
+
+  async getTipCredit(creditId: string): Promise<TipCredit | null> {
+    return this.client.get(`/rip0301/tip/${creditId}`);
+  }
+
+  // --- Atlas Land Economy ---
+
+  async registerAtlasParcel(req: RegisterAtlasParcelRequest): Promise<AtlasDeed | null> {
+    return this.client.post('/rip0301/atlas/parcel', req);
+  }
+
+  async getAtlasDeed(deedId: string): Promise<AtlasDeed | null> {
+    return this.client.get(`/rip0301/atlas/deed/${deedId}`);
+  }
+
+  async getOwnerDeeds(owner: string): Promise<AtlasDeed[]> {
+    return this.client.get(`/rip0301/atlas/deeds/${owner}`);
+  }
+
+  async transferAtlasDeed(req: TransferAtlasDeedRequest): Promise<boolean> {
+    const resp = await this.client.post('/rip0301/atlas/transfer', req);
+    return resp?.success ?? false;
+  }
+
+  async getBlockSummary(block: number): Promise<RIP0301BlockSummary> {
+    return this.client.get(`/rip0301/block/${block}`);
+  }
+}
