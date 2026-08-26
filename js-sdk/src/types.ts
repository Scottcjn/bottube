diff --git a/js-sdk/src/types.ts b/js-sdk/src/types.ts
index 0000001..0000002 100644
--- a/js-sdk/src/types.ts
+++ b/js-sdk/src/types.ts
@@ -1,3 +1,5 @@
+// RIP-0301: Tip Credits + Atlas Land Economy types
+
 export interface Video {
   id: string;
@@ -50,4 +52,60 @@ export interface PaginatedResponse<T> {
+// -----------------------------------------------------------------------
+// RIP-0301: Tip Credits
+// -----------------------------------------------------------------------
+
+export enum TipCreditStatus {
+  PENDING = 'pending',
+  MATURED = 'matured',
+  SETTLED = 'settled',
+  EXPIRED = 'expired',
+}
+
+export interface TipCredit {
+  credit_id: string;
+  sender: string;
+  receiver: string;
+  amount: number;
+  created_at_block: number;
+  status: TipCreditStatus;
+  matured_at_block?: number;
+  settled_at_block?: number;
+  attestation_hw_hash?: string;
+  abuse_flag: boolean;
+}
+
+export interface CreateTipRequest {
+  sender: string;
+  receiver: string;
+  amount: number;
+  block: number;
+  hw_attestation_hash?: string;
+  beacon_identity?: string;
+}
+
+// -----------------------------------------------------------------------
+// RIP-0301: Atlas Land Economy
+// -----------------------------------------------------------------------
+
+export enum AtlasDeedStatus {
+  ACTIVE = 'active',
+  TRANSFER_PENDING = 'transfer_pending',
+  TRANSFERRED = 'transferred',
+  SLASHED = 'slashed',
+}
+
+export interface AtlasDeed {
+  deed_id: string;
+  parcel_id: string;
+  owner: string;
+  beacon_service_id?: string;
+  status: AtlasDeedStatus;
+  acquired_at_block: number;
+  transfer_pending_to?: string;
+  transfer_pending_block?: number;
+  yield_accumulated: number;
+}
+
+export interface RegisterAtlasParcelRequest {
+  parcel_id: string;
+  owner: string;
+  beacon_service_id?: string;
+  block: number;
+}
+
+export interface TransferAtlasDeedRequest {
+  deed_id: string;
+  new_owner: string;
+  rtc_amount: number;
+  current_block: number;
+  rtc_settled: boolean;
+}
+
+export interface RIP0301BlockSummary {
+  block: number;
+  credits_matured: number;
+  credits_settled: number;
+  rtc_distributed: number;
+  founder_pool_remaining: number;
+}
