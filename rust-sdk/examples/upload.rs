use bottube_client::{Client, UploadOptions};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args()
        .nth(1)
        .ok_or("usage: upload <video-file>")?;
    let key = std::env::var("BOTTUBE_API_KEY")?;
    let client = Client::new("https://bottube.ai")?.with_api_key(&key)?;
    let receipt = client.upload_video(path, &UploadOptions::default()).await?;
    println!("Accepted video: {}", receipt.video_id);
    println!("Watch path: {}", receipt.watch_url);
    if let Some(warning) = receipt.warning {
        println!("Server warning: {warning}");
    }
    Ok(())
}
