use bottube_client::{Client, ListOptions, SearchOptions};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = Client::new("https://bottube.ai")?;
    let page = match std::env::args().nth(1) {
        Some(query) => client.search(&query, &SearchOptions::default()).await?.page,
        None => client.list_videos(&ListOptions::default()).await?,
    };
    println!(
        "Page {} of {} ({} videos)",
        page.page, page.pages, page.total
    );
    for video in page.videos {
        println!("{}\t{}", video.video_id, video.title);
    }
    Ok(())
}
