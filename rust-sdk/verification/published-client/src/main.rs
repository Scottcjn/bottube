use bottube_client::{Client, ListOptions, SearchOptions};

#[tokio::main]
async fn main() -> Result<(), bottube_client::Error> {
    let client = Client::new("https://bottube.ai")?;
    let latest = client
        .list_videos(&ListOptions {
            per_page: 1,
            ..Default::default()
        })
        .await?;
    let search = client
        .search(
            "PowerPC",
            &SearchOptions {
                per_page: 1,
                ..Default::default()
            },
        )
        .await?;
    println!("Published 0.1.0: list total = {}", latest.total);
    println!("Published 0.1.0: search total = {}", search.page.total);
    Ok(())
}
