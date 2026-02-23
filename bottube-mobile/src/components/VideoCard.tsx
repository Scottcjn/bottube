import React from "react";
import { View, Text, Pressable, StyleSheet } from "react-native";
import { FeedVideo } from "../api/client";
export function VideoCard({ video, onLike }: { video: FeedVideo; onLike: () => void }) { return (<View style={styles.card}><Text style={styles.title}>{video.title}</Text><Text style={styles.meta}>@{video.agent_name || "unknown"} · {video.views} views · {video.likes} likes</Text><Pressable onPress={onLike} style={styles.btn}><Text style={styles.btnText}>Like</Text></Pressable></View>); }
const styles = StyleSheet.create({ card: { backgroundColor: "#1b1c1f", padding: 12, borderRadius: 10, marginBottom: 10 }, title: { color: "#fff", fontSize: 16, fontWeight: "600" }, meta: { color: "#a7a8ad", marginTop: 6 }, btn: { marginTop: 10, backgroundColor: "#3ea6ff", alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 }, btnText: { color: "#111", fontWeight: "700" }});
